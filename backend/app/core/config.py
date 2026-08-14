from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    # NoDecode: without it, pydantic-settings tries to JSON-parse this env var
    # before our validator ever runs, and fails on a plain comma-separated string.
    backend_cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    # database_url has no default (fail-fast if unconfigured) and is populated
    # from the environment/.env at runtime, which mypy's synthesized __init__
    # check can't see — known false positive for required BaseSettings fields.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
