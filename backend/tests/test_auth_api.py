from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import RefreshToken, User
from app.auth.security import hash_password, hash_token

_PASSWORD = "correct horse battery staple"


def _register(client: TestClient, email: str, password: str = _PASSWORD) -> Response:
    return cast(
        Response, client.post("/api/v1/auth/register", json={"email": email, "password": password})
    )


def _login(client: TestClient, email: str, password: str = _PASSWORD) -> Response:
    return cast(
        Response, client.post("/api/v1/auth/login", json={"email": email, "password": password})
    )


def _delete_user_by_email(db_session: Session, email: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    if user is not None:
        db_session.delete(user)
        db_session.commit()


def test_register_creates_a_user_and_never_returns_the_password(
    client: TestClient, db_session: Session
) -> None:
    response = _register(client, "register-test@example.com")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "register-test@example.com"
    assert "password" not in body
    assert "hashed_password" not in body

    user = db_session.scalar(select(User).where(User.email == "register-test@example.com"))
    assert user is not None
    assert user.hashed_password != _PASSWORD

    _delete_user_by_email(db_session, "register-test@example.com")


def test_register_normalizes_email_to_lowercase(
    client: TestClient, db_session: Session
) -> None:
    response = _register(client, "MixedCase@Example.com")

    assert response.status_code == 201
    assert response.json()["email"] == "mixedcase@example.com"

    _delete_user_by_email(db_session, "mixedcase@example.com")


def test_register_rejects_a_duplicate_email(client: TestClient, db_session: Session) -> None:
    _register(client, "dup-register-test@example.com")

    response = _register(client, "dup-register-test@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"

    _delete_user_by_email(db_session, "dup-register-test@example.com")


def test_register_rejects_a_too_short_password(client: TestClient) -> None:
    response = _register(client, "short-pw-test@example.com", password="short")
    assert response.status_code == 422


def test_login_with_wrong_password_and_nonexistent_email_return_identical_errors(
    client: TestClient, db_session: Session
) -> None:
    """The security property that matters most here: a failed login must
    never let a caller distinguish "wrong password" from "no such
    account" - otherwise login becomes an email-enumeration oracle.
    """
    _register(client, "login-test@example.com")

    wrong_password = _login(client, "login-test@example.com", password="totally wrong password")
    nonexistent = _login(client, "does-not-exist-at-all@example.com", password="whatever")

    assert wrong_password.status_code == 401
    assert nonexistent.status_code == 401
    assert wrong_password.json() == nonexistent.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"

    _delete_user_by_email(db_session, "login-test@example.com")


def test_login_rejects_a_deactivated_user_with_the_same_generic_error(
    client: TestClient, db_session: Session
) -> None:
    user = User(email="deactivated-test@example.com", hashed_password=hash_password(_PASSWORD))
    user.is_active = False
    db_session.add(user)
    db_session.commit()

    response = _login(client, "deactivated-test@example.com")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"

    _delete_user_by_email(db_session, "deactivated-test@example.com")


def test_login_with_correct_credentials_issues_a_token_pair(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "login-success-test@example.com")

    response = _login(client, "login-success-test@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    _delete_user_by_email(db_session, "login-success-test@example.com")


def test_refresh_issues_a_new_access_token_for_a_valid_refresh_token(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "refresh-test@example.com")
    refresh_token = _login(client, "refresh-test@example.com").json()["refresh_token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]

    _delete_user_by_email(db_session, "refresh-test@example.com")


def test_refresh_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


def test_refresh_rejects_a_genuinely_expired_token(
    client: TestClient, db_session: Session
) -> None:
    """Distinct from the garbage-token case: this token is well-formed and
    was once valid, but its expires_at has passed.
    """
    user = User(email="expired-refresh-test@example.com", hashed_password=hash_password(_PASSWORD))
    db_session.add(user)
    db_session.flush()
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token("expired-token-value"),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.commit()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "expired-token-value"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"

    _delete_user_by_email(db_session, "expired-refresh-test@example.com")


def test_refresh_rejects_a_revoked_token(client: TestClient, db_session: Session) -> None:
    _register(client, "revoke-test@example.com")
    refresh_token = _login(client, "revoke-test@example.com").json()["refresh_token"]
    client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"

    _delete_user_by_email(db_session, "revoke-test@example.com")


def test_logout_revokes_the_token(client: TestClient, db_session: Session) -> None:
    _register(client, "logout-test@example.com")
    refresh_token = _login(client, "logout-test@example.com").json()["refresh_token"]

    response = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    assert response.status_code == 204
    token = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    assert token is not None
    assert token.revoked_at is not None

    _delete_user_by_email(db_session, "logout-test@example.com")


def test_logout_is_idempotent_for_an_already_revoked_token(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "double-logout-test@example.com")
    refresh_token = _login(client, "double-logout-test@example.com").json()["refresh_token"]

    first = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    second = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    assert first.status_code == 204
    assert second.status_code == 204

    _delete_user_by_email(db_session, "double-logout-test@example.com")


def test_logout_with_a_token_that_never_existed_still_returns_204(client: TestClient) -> None:
    """Logout must not be an oracle for whether a token was ever real."""
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "never-existed-at-all"})
    assert response.status_code == 204
