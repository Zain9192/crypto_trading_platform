from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class TokenError(ValueError):
    """Raised when an authentication token cannot be trusted."""


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_one_time_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: int, role: str, settings: Settings) -> tuple[str, datetime]:
    settings.validate_auth_secrets()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), expires_at


def create_refresh_token(user_id: int, settings: Settings) -> tuple[str, str, datetime]:
    settings.validate_auth_secrets()
    jti = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_refresh_token_minutes)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str, expected_type: str, settings: Settings) -> dict[str, object]:
    settings.validate_auth_secrets()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")
    if not payload.get("sub"):
        raise TokenError("Token subject is missing")
    return payload


def _fernet(settings: Settings) -> Fernet:
    settings.validate_auth_secrets()
    try:
        return Fernet(settings.auth_data_encryption_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("AUTH_DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_auth_secret(value: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_auth_secret(value: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenError("Stored authentication secret cannot be decrypted") from exc
