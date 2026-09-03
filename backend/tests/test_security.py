from datetime import timezone

from app.core.config import Settings
from app.core.security import create_access_token, decode_token, hash_password, verify_password


TEST_FERNET_KEY = "65ujGo4u-rd5tR5SJEB0mvwCv4DZIuk6S7jgpQ8xOEc="


def test_password_hash_uses_bcrypt_cost_12() -> None:
    encoded = hash_password("StrongPass123!")
    parts = encoded.split("$")
    assert parts[1].startswith("2")
    assert int(parts[2]) >= 12
    assert verify_password("StrongPass123!", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_round_trip() -> None:
    settings = Settings(
        app_env="test",
        jwt_secret_key="test-only-secret-key-that-is-at-least-32-characters-long",
        auth_data_encryption_key=TEST_FERNET_KEY,
    )
    token, expires_at = create_access_token(42, "trader", settings)
    payload = decode_token(token, "access", settings)

    assert payload["sub"] == "42"
    assert payload["role"] == "trader"
    assert expires_at.tzinfo == timezone.utc
