"""JWT access-token issuance/verification, and opaque refresh-token
generation.

Access tokens are stateless JWTs - short-lived (~15 min), verified with
no DB hit, carrying just the user id and an expiry. Refresh tokens are
deliberately NOT JWTs: they're high-entropy random strings whose hash
(see app/auth/security.py) is checked against the RefreshToken table.
That's what makes revocation possible - logout, a compromised token -
without a JWT blocklist or Redis-backed session state, matching the
original architecture's stated reasoning for this split.
"""

import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings


class InvalidAccessTokenError(Exception):
    """Covers every way an access token can be unusable - expired,
    tampered, wrong signature, malformed payload. Callers don't need to
    distinguish which; all of them mean "re-authenticate".
    """


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Returns the user id encoded in a valid, unexpired access token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError("Invalid or expired access token") from exc
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidAccessTokenError("Invalid access token payload") from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
