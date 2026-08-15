"""FastAPI dependencies that resolve the caller's identity from a bearer
access token.

Two variants, because not every route needs the same thing:

- get_current_user: auth is required. No token -> 401 "not_authenticated".
  A present-but-bad token (expired, tampered, unknown user, deactivated
  user) -> 401 "invalid_access_token". These are deliberately DIFFERENT
  codes here (unlike login/refresh's deliberate error-uniformity to avoid
  email enumeration) - there's no enumeration risk in telling a caller
  "you're not logged in" vs. "your session is bad", and the distinction
  is genuinely useful for a client deciding what to do next.

- get_current_user_optional: for routes like POST /calculations that work
  both logged in and anonymous. Never raises - not on a missing token
  (ordinary anonymous use) and not on a bad one either. An earlier
  version of this dependency treated a present-but-invalid token as an
  error, on the reasoning that silently downgrading to anonymous would
  hide a confusing "why didn't this save to my history" failure. That
  reasoning was correct for what it optimized for, but wrong for this
  endpoint specifically: raising means anyone who leaves the calculator
  open past the access token's ~15-minute lifetime can no longer
  calculate AT ALL, not just "won't be saved" - which breaks the phase's
  own design assumption that the core tool must always work without a
  valid session. Returns an OptionalAuthResult instead, so the caller
  still gets the "was a bad token presented" signal (to surface a "your
  session expired, log in again" message) without the request itself
  ever failing over it.
"""

from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.tokens import InvalidAccessTokenError, decode_access_token
from app.core.exceptions import AppError
from app.db.session import get_db

# auto_error=False: FastAPI's own default behavior for a missing header is
# to raise its own 403 with its own error shape. We want "missing" to be a
# normal, handled case (different outcomes for the two dependencies below),
# not an exception thrown before our code ever runs.
_bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_user(db: Session, token: str) -> User:
    try:
        user_id = decode_access_token(token)
    except InvalidAccessTokenError as exc:
        raise AppError(
            "Invalid or expired access token", code="invalid_access_token", status_code=401
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(
            "Invalid or expired access token", code="invalid_access_token", status_code=401
        )
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError("Authentication required", code="not_authenticated", status_code=401)
    return _resolve_user(db, credentials.credentials)


@dataclass
class OptionalAuthResult:
    user: User | None
    # True only when a bearer token was actually presented and rejected -
    # distinct from the ordinary "no token at all" anonymous case, which
    # leaves this False. Lets a caller tell "never logged in" apart from
    # "was logged in, session lapsed" without the request having to fail.
    token_rejected: bool


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> OptionalAuthResult:
    if credentials is None:
        return OptionalAuthResult(user=None, token_rejected=False)
    try:
        user = _resolve_user(db, credentials.credentials)
    except AppError:
        return OptionalAuthResult(user=None, token_rejected=True)
    return OptionalAuthResult(user=user, token_rejected=False)
