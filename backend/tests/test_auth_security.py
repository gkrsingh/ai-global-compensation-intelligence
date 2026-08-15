from app.auth.security import hash_password, hash_token, verify_password


def test_hash_password_produces_an_argon2id_hash() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert hashed != "correct horse battery staple"


def test_verify_password_accepts_the_correct_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_a_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_password_rejects_an_empty_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("", hashed) is False


def test_hashing_the_same_password_twice_produces_different_hashes() -> None:
    """Proves a random salt per hash, not naive/unsalted hashing - two
    users who happen to choose the same password must not end up with
    identical hash values in the database.
    """
    hashed_a = hash_password("correct horse battery staple")
    hashed_b = hash_password("correct horse battery staple")

    assert hashed_a != hashed_b
    assert verify_password("correct horse battery staple", hashed_a) is True
    assert verify_password("correct horse battery staple", hashed_b) is True


def test_hash_token_is_a_deterministic_64_char_sha256_hex_digest() -> None:
    digest = hash_token("some-raw-refresh-token-value")
    assert len(digest) == 64
    assert digest == hash_token("some-raw-refresh-token-value")


def test_hash_token_differs_for_different_tokens() -> None:
    assert hash_token("token-a") != hash_token("token-b")
