"""Password hashing with Argon2.

Argon2id is the design doc's chosen algorithm (§9.8). ``argon2-cffi`` handles
salting internally and stores all parameters inside the hash string, so verify
needs only the hash and the candidate password. Hashes are never logged or
returned in responses.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# A single shared hasher with library defaults (Argon2id). Tuning parameters
# (time/memory cost) can be centralized here later without touching callers.
_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Return an Argon2 hash for ``plain_password`` (salt embedded in the hash)."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True iff ``plain_password`` matches ``hashed_password``.

    Returns False (never raises) on mismatch or a malformed stored hash, so
    callers get a simple boolean and there is no exception-based timing signal.
    """
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, Exception):  # noqa: BLE001
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Whether a stored hash should be upgraded to current parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except Exception:  # noqa: BLE001
        return False
