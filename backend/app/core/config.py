from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Crypto Trading Platform"
    app_env: str = "development"
    rate_limit_enabled: bool = True
    api_rate_limit_per_minute: int = Field(default=600,ge=1)
    auth_rate_limit_per_minute: int = Field(default=20,ge=1)
    request_max_bytes: int = Field(default=1048576,ge=1024)
    trusted_proxy_cidrs: str = ''
    cors_origins: str = 'http://localhost:5173' 
    api_v1_prefix: str = "/api/v1"

    postgres_db: str = "crypto_trading"
    postgres_user: str = "crypto_user"
    postgres_password: str = "change_me"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    mongo_db: str = "crypto_market"
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str = ""
    mongo_password: str = ""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    sentry_dsn: SecretStr = SecretStr("")

    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_minutes: int = 1440
    jwt_refresh_token_minutes: int = 10080
    email_verification_token_minutes: int = 1440
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    auth_data_encryption_key: str = ""
    totp_issuer: str = "AI Crypto Trading Platform"

    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    binance_market_base_url: str = "https://api.binance.com"
    market_default_quote_asset: str = "USDT"
    market_refresh_seconds: int = Field(default=30, ge=1)
    market_history_refresh_seconds: int = Field(default=900, ge=60)
    market_history_candle_limit: int = Field(default=500, ge=20, le=1000)
    market_ingestion_request_spacing_seconds: float = Field(default=0.25, ge=0.01)
    market_cache_ttl_seconds: int = 25
    ohlcv_cache_ttl_seconds: int = 60
    market_http_timeout_seconds: float = 10.0

    exchange_encryption_key: SecretStr = SecretStr("")
    notification_email_provider: Literal['disabled', 'smtp', 'sendgrid'] = 'disabled'
    notification_email_from: str = ''
    notification_smtp_host: str = ''
    notification_smtp_port: int = Field(default=587, ge=1, le=65535)
    notification_smtp_username: str = ''
    notification_smtp_password: SecretStr = SecretStr('')
    notification_sendgrid_key: SecretStr = SecretStr('')
    prediction_artifact_dir: str = "model_artifacts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def mongo_uri(self) -> str:
        credentials = (
            f"{quote(self.mongo_user, safe='')}:{quote(self.mongo_password, safe='')}@"
            if self.mongo_user and self.mongo_password else ""
        )
        suffix = "/?authSource=admin" if credentials else ""
        return f"mongodb://{credentials}{self.mongo_host}:{self.mongo_port}{suffix}"

    def validate_auth_secrets(self) -> None:
        if len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
        if not self.auth_data_encryption_key:
            raise RuntimeError("AUTH_DATA_ENCRYPTION_KEY is required")


@lru_cache
def get_settings() -> Settings:
    return Settings()
