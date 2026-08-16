import os
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # env_file is read from ENV_FILE (falling back to ".env") rather than
    # hardcoded, specifically so tests/conftest.py can redirect this at
    # .env.test instead. Without this, an optional field with no value in
    # .env.test (like gemini_api_key/anthropic_api_key - deliberately
    # absent, expected to resolve to None) falls through to pydantic-
    # settings' own env_file fallback, which would otherwise read the
    # REAL .env directly for just that field - confirmed as a genuine
    # bug, not a hypothetical: a test asserting the "AI not configured"
    # path instead made a real Gemini API call, because it silently
    # picked up the real key from .env even though .env.test never
    # mentions it and conftest.py's load_dotenv(override=True) only
    # populates os.environ with what .env.test actually defines.
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

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

    # Which AIProvider get_ai_provider() (app/ai/api.py) instantiates -
    # "gemini" or "anthropic". Both concrete providers stay fully wired
    # and reachable regardless of this setting (a genuine proof that the
    # AIProvider interface is actually swappable, not just built to look
    # that way) - this just picks which one is live by default. Defaults
    # to "gemini": free-tier suitable for this project's volume, per the
    # Phase 8 research that also ruled out gemini-2.5-flash (no longer
    # available to new users) and plain gemini-3.5-flash (a thinking
    # model that can exhaust its token budget on invisible reasoning
    # with no visible output - confirmed with a real test call, not
    # assumed).
    ai_provider: str = "gemini"

    # Both API keys are deliberately optional with no fail-fast, unlike
    # jwt_secret_key/database_url: AI insight is a narrow, gateable
    # feature layered on top of an app that's fully functional without
    # it (every other endpoint, and the automated test suite, must keep
    # working with both unset - CI never provisions a real key, since
    # tests mock the provider and must never make a live call). Only the
    # AI code path itself needs to check for the active provider's key
    # and fail explicitly there if it's missing.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"

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
