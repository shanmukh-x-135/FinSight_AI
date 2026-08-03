"""Unit tests for password hashing and JWT utilities (no DB, no HTTP)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.shared.security.jwt import (
    DecodedToken,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.shared.security.passwords import hash_password, verify_password
from config.settings import settings


# ----- Passwords -----------------------------------------------------------
def test_password_hash_round_trip() -> None:
    hashed = hash_password("S3curePass!")
    assert hashed != "S3curePass!"          # never stored in plaintext
    assert hashed.startswith("$argon2")     # Argon2 encoded form
    assert verify_password("S3curePass!", hashed) is True


def test_password_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct-horse")
    assert verify_password("wrong-horse", hashed) is False


def test_password_verify_handles_malformed_hash() -> None:
    # Never raises — returns False on a garbage stored hash.
    assert verify_password("anything", "not-a-real-hash") is False


def test_two_hashes_of_same_password_differ() -> None:
    # Distinct random salts → distinct hashes.
    assert hash_password("same") != hash_password("same")


def test_needs_rehash_false_for_current_hash_and_garbage() -> None:
    from app.shared.security.passwords import needs_rehash

    assert needs_rehash(hash_password("pw")) is False
    assert needs_rehash("not-a-hash") is False


# ----- JWT -----------------------------------------------------------------
def test_access_token_encodes_and_decodes() -> None:
    token = create_access_token(42)
    decoded = decode_token(token, expected_type="access")
    assert isinstance(decoded, DecodedToken)
    assert decoded.subject == "42"
    assert decoded.token_type == "access"
    assert decoded.jti is None


def test_refresh_token_carries_jti() -> None:
    token, jti = create_refresh_token(7)
    decoded = decode_token(token, expected_type="refresh")
    assert decoded.subject == "7"
    assert decoded.token_type == "refresh"
    assert decoded.jti == jti


def test_decode_rejects_wrong_expected_type() -> None:
    access = create_access_token(1)
    with pytest.raises(TokenError):
        decode_token(access, expected_type="refresh")


def test_decode_rejects_tampered_signature() -> None:
    token = create_access_token(1)
    with pytest.raises(TokenError):
        decode_token(token + "tamper", expected_type="access")


def test_decode_rejects_expired_token() -> None:
    past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(
        {"sub": "1", "type": "access", "iat": past, "exp": past},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        decode_token(expired, expected_type="access")


def test_decode_rejects_foreign_secret() -> None:
    foreign = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
        },
        "a-different-secret",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        decode_token(foreign, expected_type="access")
