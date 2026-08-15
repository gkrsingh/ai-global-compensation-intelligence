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
  both logged in and anonymous. No token -> None, silently anonymous,
  exactly as intended. A present-but-bad token is still an ERROR, not
  silently downgraded to anonymous - if a caller sends credentials, an
  expired token would otherwise fail silently as "your calculation just
  didn't get saved to your history", which is a confusing way to
  discover you've been logged out.
"""

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


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return _resolve_user(db, credentials.credentials)
