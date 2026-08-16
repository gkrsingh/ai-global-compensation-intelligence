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

    # No default, same fail-fast-if-unconfigured treatment as database_url -
    # this signs every access token issued, so an accidental hardcoded
    # default would be a real vulnerability, not just a convenience.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Unlike jwt_secret_key/database_url, deliberately optional with no
    # fail-fast: AI insight is a narrow, gateable feature layered on top
    # of an app that's fully functional without it (every other endpoint,
    # and the automated test suite, must keep working with this unset -
    # CI never provisions a real key, since tests mock the provider and
    # must never make a live call). Only the AI code path itself needs to
    # check for its presence and fail explicitly there if it's missing.
    anthropic_api_key: str | None = None
    ai_model: str = "claude-sonnet-5"

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
