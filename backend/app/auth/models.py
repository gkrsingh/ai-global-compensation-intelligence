from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Deliberately minimal - email, password hash, activity flag, nothing
    else. Kept decoupled from any future UserProfile (role, location,
    experience level, ...) per the original domain model: that's identity
    metadata a later phase might add, not something auth itself needs to
    know about.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """A hash of the refresh token, never the raw token - the same
    rationale as password hashing, but not the same algorithm: a refresh
    token is a high-entropy random secret we generate ourselves (unlike a
    user-chosen password), so a fast cryptographic hash (SHA-256, see
    app/auth/security.py) is the right tool here, not the slow/memory-hard
    argon2 used for passwords. revoked_at (nullable) is what makes logout
    and compromised-token revocation possible without Redis-backed session
    state - the whole reason this table exists instead of just trusting a
    long-lived JWT.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
