from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    refresh_token_expiry,
)
from app.core.config import settings


def test_create_and_decode_access_token_round_trips_the_user_id() -> None:
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_access_token_lifetime_matches_the_configured_minutes() -> None:
    token = create_access_token(user_id=1)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    lifetime_seconds = payload["exp"] - payload["iat"]
    assert lifetime_seconds == settings.access_token_expire_minutes * 60


def test_decode_access_token_rejects_an_expired_token() -> None:
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(UTC) - timedelta(minutes=30),
            "exp": datetime.now(UTC) - timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(expired)


def test_decode_access_token_rejects_a_token_signed_with_a_different_secret() -> None:
    """Not just "does it check exp" - proves signature verification is
    actually enforced, not skipped.
    """
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(minutes=15)},
        "a-completely-different-secret-nobody-would-guess",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_garbage() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not.a.jwt")


def test_decode_access_token_rejects_a_validly_signed_token_with_a_malformed_sub_claim() -> None:
    """A correctly signed, unexpired token is still not trustworthy if its
    payload doesn't shape up - e.g. hand-crafted or from a future version
    of this code that changed the claim's meaning.
    """
    token = jwt.encode(
        {"sub": "not-a-number", "exp": datetime.now(UTC) + timedelta(minutes=15)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_a_token_with_no_sub_claim_at_all() -> None:
    token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=15)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_generate_refresh_token_produces_high_entropy_unique_values() -> None:
    a = generate_refresh_token()
    b = generate_refresh_token()
    assert a != b
    assert len(a) > 30


def test_refresh_token_expiry_matches_the_configured_number_of_days() -> None:
    expiry = refresh_token_expiry()
    expected = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    assert abs((expiry - expected).total_seconds()) < 5
