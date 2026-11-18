import functools
import secrets

import argon2

PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128

_hasher = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@functools.cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe())


def verify_password(password_hash: str | None, password: str) -> bool:
    """Run exactly one argon2 verification, against a dummy hash when there is no hash, so timing reveals nothing."""
    try:
        return _hasher.verify(password_hash or _dummy_hash(), password) and password_hash is not None
    except argon2.exceptions.VerificationError, argon2.exceptions.InvalidHashError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
