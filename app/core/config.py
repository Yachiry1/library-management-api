from functools import lru_cache
from typing import Annotated

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "library-api"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://library:library@localhost:5432/library"
    test_database_url: str | None = None

    jwt_secret_key: Annotated[str, Field(min_length=32)]
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: Annotated[int, Field(gt=0)] = 15
    refresh_token_expire_days: Annotated[int, Field(gt=0)] = 30

    max_csv_upload_bytes: Annotated[int, Field(gt=0)] = 1_048_576
    cors_origins: Annotated[list[str], NoDecode] = []

    rate_limit_enabled: bool = False
    redis_url: AnyUrl | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        msg = "CORS_ORIGINS must be a comma-separated string"
        raise ValueError(msg)


@lru_cache
def get_settings() -> Settings:
    return Settings()
