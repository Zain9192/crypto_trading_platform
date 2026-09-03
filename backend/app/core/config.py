from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Crypto Trading Platform"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    postgres_db: str = "crypto_trading"
    postgres_user: str = "crypto_user"
    postgres_password: str = "change_me"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    mongo_db: str = "crypto_market"
    mongo_host: str = "localhost"
    mongo_port: int = 27017

    redis_host: str = "localhost"
    redis_port: int = 6379

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 1440
    jwt_refresh_token_minutes: int = 10080
    email_verification_token_minutes: int = 1440
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    auth_data_encryption_key: str = ""
    totp_issuer: str = "AI Crypto Trading Platform"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def validate_auth_secrets(self) -> None:
        if len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
        if not self.auth_data_encryption_key:
            raise RuntimeError("AUTH_DATA_ENCRYPTION_KEY is required")


@lru_cache
def get_settings() -> Settings:
    return Settings()
