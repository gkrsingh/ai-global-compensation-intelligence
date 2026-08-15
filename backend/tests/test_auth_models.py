from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import RefreshToken, User
from app.auth.security import hash_password, hash_token


def _make_user(db_session: Session, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("irrelevant-for-this-test"))
    db_session.add(user)
    db_session.flush()
    return user


def test_user_email_must_be_unique(db_session: Session) -> None:
    _make_user(db_session, "dup-email-test@example.com")

    dup = User(
        email="dup-email-test@example.com",
        hashed_password=hash_password("irrelevant-for-this-test"),
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_new_user_defaults_to_active(db_session: Session) -> None:
    user = _make_user(db_session, "defaults-test@example.com")
    assert user.is_active is True


def test_refresh_token_persists_with_a_hashed_token_and_expiry(db_session: Session) -> None:
    user = _make_user(db_session, "refresh-token-test@example.com")
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token("raw-token-value"),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(token)
    db_session.flush()

    assert token.id is not None
    assert token.revoked_at is None


def test_refresh_token_hash_must_be_unique(db_session: Session) -> None:
    user = _make_user(db_session, "dup-token-hash-test@example.com")
    shared_hash = hash_token("shared-raw-token-value")
    expires_at = datetime.now(UTC) + timedelta(days=30)
    db_session.add(RefreshToken(user_id=user.id, token_hash=shared_hash, expires_at=expires_at))
    db_session.flush()

    db_session.add(RefreshToken(user_id=user.id, token_hash=shared_hash, expires_at=expires_at))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_deleting_a_user_cascades_to_their_refresh_tokens(db_session: Session) -> None:
    user = _make_user(db_session, "cascade-test@example.com")
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token("raw-token-for-cascade-test"),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(token)
    db_session.flush()
    token_id = token.id

    db_session.delete(user)
    db_session.flush()

    assert db_session.get(RefreshToken, token_id) is None
