"""Password and refresh-token hashing primitives.

Password hashing uses argon2id (via argon2-cffi), not bcrypt: OWASP's
current Password Storage Cheat Sheet lists Argon2id as the first-choice
recommendation - it's memory-hard, which makes GPU/ASIC-accelerated
cracking of a leaked hash meaningfully more expensive than bcrypt's
purely-CPU-bound design. argon2-cffi is a mature, actively maintained
binding with sane defaults (its PasswordHasher picks parameters following
argon2's own recommended baseline). It also sidesteps bcrypt's well-known
72-byte silent-truncation gotcha, which has caused real security bugs in
other codebases (two passwords sharing a 72-byte prefix hash identically).

Refresh-token hashing uses plain SHA-256, deliberately NOT argon2: a
refresh token is a high-entropy secret we generate ourselves (not a
user-chosen password), so there's no offline brute-force risk to defend
against with a slow/memory-hard hash - the threat model is "don't store
the raw secret verbatim in the DB", not "resist guessing". A fast hash
also matters here because every use of a refresh token (login,
refresh, logout) does a lookup by this hash.
"""

import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _password_hasher.verify(hashed_password, password)
    except VerifyMismatchError:
        return False


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
