import base64

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.ops.preflight import validate


def test_production_preflight_accepts_generated_keys_and_rejects_placeholders():
    values = dict(app_env="production", postgres_password="p" * 32,
                  mongo_user="crypto", mongo_password="m" * 32, redis_password="r" * 32,
                  jwt_secret_key="j" * 32,
                  auth_data_encryption_key=Fernet.generate_key().decode(),
                  exchange_encryption_key=base64.b64encode(b"x" * 32).decode())
    validate(Settings(**values))
    with pytest.raises(RuntimeError, match="jwt_secret_key"):
        validate(Settings(**{**values, "jwt_secret_key": "replace-with-a-long-random-secret-at-least-32-characters"}))
    with pytest.raises(RuntimeError, match="EXCHANGE_ENCRYPTION_KEY"):
        validate(Settings(**{**values, "exchange_encryption_key": "invalid"}))
