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


def test_get_current_user_returns_the_user_for_a_valid_token(db_session: Session) -> None:
    user = _make_user(db_session, "dep-required-valid-test@example.com")
    token = create_access_token(user.id)

    resolved = get_current_user(credentials=_bearer(token), db=db_session)

    assert resolved.id == user.id
    assert resolved.email == "dep-required-valid-test@example.com"

    db_session.delete(user)
    db_session.commit()


def test_get_current_user_rejects_a_garbage_token(db_session: Session) -> None:
    with pytest.raises(AppError) as exc_info:
        get_current_user(credentials=_bearer("not-a-real-token"), db=db_session)
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


def test_get_current_user_optional_with_no_credentials_is_anonymous_and_not_rejected(
    db_session: Session,
) -> None:
    result = get_current_user_optional(credentials=None, db=db_session)
    assert result.user is None
    assert result.token_rejected is False


def test_get_current_user_optional_returns_the_user_for_a_valid_token(
    db_session: Session,
) -> None:
    user = _make_user(db_session, "dep-optional-valid-test@example.com")
    token = create_access_token(user.id)

    result = get_current_user_optional(credentials=_bearer(token), db=db_session)

    assert result.user is not None
    assert result.user.id == user.id
    assert result.token_rejected is False

    db_session.delete(user)
    db_session.commit()


def test_get_current_user_optional_never_raises_on_a_bad_token_and_flags_it_as_rejected(
    db_session: Session,
) -> None:
    """The core behavior this dependency exists for: the calculate
    endpoint must keep working even with a stale access token left over
    from a browser tab open past its 15-minute lifetime - raising here
    would silently break the whole feature for a user who is, for all
    practical purposes, just using the tool logged out. token_rejected
    still carries the "this wasn't just an ordinary anonymous request"
    signal, so a caller can act on it without the request failing.
    """
    result = get_current_user_optional(credentials=_bearer("not-a-real-token"), db=db_session)
    assert result.user is None
    assert result.token_rejected is True


def test_get_current_user_optional_never_raises_on_an_expired_token(db_session: Session) -> None:
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(UTC) - timedelta(minutes=30),
            "exp": datetime.now(UTC) - timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    result = get_current_user_optional(credentials=_bearer(expired), db=db_session)
    assert result.user is None
    assert result.token_rejected is True


def test_get_current_user_optional_never_raises_for_a_deactivated_users_token(
    db_session: Session,
) -> None:
    user = _make_user(db_session, "dep-optional-deactivated-test@example.com", is_active=False)
    token = create_access_token(user.id)

    result = get_current_user_optional(credentials=_bearer(token), db=db_session)

    assert result.user is None
    assert result.token_rejected is True

    db_session.delete(user)
    db_session.commit()
