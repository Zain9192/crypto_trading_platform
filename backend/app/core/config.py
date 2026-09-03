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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
