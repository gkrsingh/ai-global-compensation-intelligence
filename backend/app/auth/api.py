from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import RefreshToken, User
from app.auth.schemas import (
    AccessTokenOut,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairOut,
    UserOut,
)
from app.auth.security import hash_password, hash_token, verify_password
from app.auth.tokens import create_access_token, generate_refresh_token, refresh_token_expiry
from app.core.exceptions import AppError
from app.db.session import get_db

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise AppError(
            "An account with this email already exists",
            code="email_already_registered",
            status_code=409,
        )

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _issue_token_pair(db: Session, user: User) -> TokenPairOut:
    access_token = create_access_token(user.id)
    raw_refresh_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=refresh_token_expiry(),
        )
    )
    db.commit()
    return TokenPairOut(access_token=access_token, refresh_token=raw_refresh_token)


@router.post("/login", response_model=TokenPairOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPairOut:
    user = db.scalar(select(User).where(User.email == payload.email))
    # Identical error for "no such user", "wrong password", and "account
    # disabled" - a failed login must never reveal which of those it was,
    # or an attacker can enumerate registered emails one guess at a time.
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise AppError("Invalid email or password", code="invalid_credentials", status_code=401)
    return _issue_token_pair(db, user)


def _get_valid_refresh_token(db: Session, raw_token: str) -> RefreshToken:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    # Same error for "no such token", "revoked", "expired", and "owning
    # user deactivated" - same enumeration-avoidance reasoning as login.
    if (
        token is None
        or token.revoked_at is not None
        or token.expires_at < datetime.now(UTC)
        or not token.user.is_active
    ):
        raise AppError(
            "Invalid or expired refresh token", code="invalid_refresh_token", status_code=401
        )
    return token


@router.post("/refresh", response_model=AccessTokenOut)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenOut:
    token = _get_valid_refresh_token(db, payload.refresh_token)
    return AccessTokenOut(access_token=create_access_token(token.user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    # Idempotent by design: an already-revoked or never-existent token
    # still 204s. Logout confirming or denying token validity would be an
    # oracle for an attacker probing tokens, and there's no legitimate
    # reason a client needs to know which case it was.
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(payload.refresh_token))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        db.commit()
