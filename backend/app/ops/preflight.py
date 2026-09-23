"""Refuse a production deployment with placeholder or malformed secrets."""
import base64
import binascii

from cryptography.fernet import Fernet

from app.core.config import get_settings


def validate(settings):
    if settings.app_env != "production":
        raise RuntimeError("Production stack requires APP_ENV=production")
    for name in ("postgres_password", "mongo_password", "redis_password", "jwt_secret_key"):
        value = getattr(settings, name)
        if len(value) < 24 or value.lower().startswith(("replace", "change_me", "test-")):
            raise RuntimeError(f"Configure a strong {name}")
    if not settings.mongo_user:
        raise RuntimeError("Configure MongoDB authentication")
    try:
        Fernet(settings.auth_data_encryption_key.encode())
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Configure a valid AUTH_DATA_ENCRYPTION_KEY") from exc
    try:
        key = base64.b64decode(settings.exchange_encryption_key.get_secret_value(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Configure a valid EXCHANGE_ENCRYPTION_KEY") from exc
    if len(key) != 32:
        raise RuntimeError("EXCHANGE_ENCRYPTION_KEY must contain 32 bytes")


if __name__ == "__main__":
    validate(get_settings())
    print("Production environment preflight passed")
