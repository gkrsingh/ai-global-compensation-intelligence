from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.models import User
from app.auth.security import hash_password
from app.auth.tokens import create_access_token
from app.core.config import settings
from app.core.exceptions import AppError


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_user(db_session: Session, email: str, *, is_active: bool = True) -> User:
    user = User(email=email, hashed_password=hash_password("irrelevant-for-this-test"))
    user.is_active = is_active
    db_session.add(user)
    db_session.flush()
    return user


def test_get_current_user_raises_not_authenticated_with_no_credentials(
    db_session: Session,
) -> None:
    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=None, db=db_session)
    assert exc_info.value.code == "not_authenticated"
    assert exc_info.value.status_code == 401


def test_get_current_user_optional_returns_none_with_no_credentials(db_session: Session) -> None:
    assert get_current_user_optional(credentials=None, db=db_session) is None


def test_get_current_user_returns_the_user_for_a_valid_token(db_session: Session) -> None:
    user = _make_user(db_session, "dep-required-valid-test@example.com")
    token = create_access_token(user.id)

    resolved = get_current_user(credentials=_bearer(token), db=db_session)

    assert resolved.id == user.id
    assert resolved.email == "dep-required-valid-test@example.com"

    db_session.delete(user)
    db_session.commit()


def test_get_current_user_optional_returns_the_user_for_a_valid_token(
    db_session: Session,
) -> None:
    user = _make_user(db_session, "dep-optional-valid-test@example.com")
    token = create_access_token(user.id)

    resolved = get_current_user_optional(credentials=_bearer(token), db=db_session)

    assert resolved is not None
    assert resolved.id == user.id

    db_session.delete(user)
    db_session.commit()


def test_get_current_user_rejects_a_garbage_token(db_session: Session) -> None:
    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=_bearer("not-a-real-token"), db=db_session)
    assert exc_info.value.code == "invalid_access_token"
    assert exc_info.value.status_code == 401


def test_get_current_user_optional_does_NOT_silently_downgrade_a_bad_token_to_anonymous(
    db_session: Session,
) -> None:
    """The whole point of this dependency: presenting credentials that
    turn out to be bad must be a visible error, not a silent fallback to
    "treated as logged out" - that would be a confusing way to discover
    your session expired.
    """
    with pytest.raises(AppError) as exc_info:
        get_current_user_optional(credentials=_bearer("not-a-real-token"), db=db_session)
    assert exc_info.value.code == "invalid_access_token"
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_an_expired_token(db_session: Session) -> None:
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(UTC) - timedelta(minutes=30),
            "exp": datetime.now(UTC) - timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=_bearer(expired), db=db_session)
    assert exc_info.value.code == "invalid_access_token"


def test_get_current_user_rejects_a_token_for_a_user_that_no_longer_exists(
    db_session: Session,
) -> None:
    user = _make_user(db_session, "dep-deleted-user-test@example.com")
    token = create_access_token(user.id)
    db_session.delete(user)
    db_session.commit()

    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=_bearer(token), db=db_session)
    assert exc_info.value.code == "invalid_access_token"


def test_get_current_user_rejects_a_token_for_a_deactivated_user(db_session: Session) -> None:
    user = _make_user(db_session, "dep-deactivated-test@example.com", is_active=False)
    token = create_access_token(user.id)

    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=_bearer(token), db=db_session)
    assert exc_info.value.code == "invalid_access_token"

    db_session.delete(user)
    db_session.commit()
