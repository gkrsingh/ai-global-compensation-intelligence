import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Must run before `app` is imported anywhere below: Settings is built at
# import time, so DATABASE_URL has to point at compintel_test (not the .env
# default of compintel_dev) before app.core.config ever loads.
_ENV_TEST_PATH = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(_ENV_TEST_PATH, override=True)

# load_dotenv only sets keys that .env.test actually defines - it can't
# make a key "absent" for a field that IS defined in the real .env but
# deliberately isn't in .env.test (e.g. GEMINI_API_KEY/ANTHROPIC_API_KEY,
# expected to resolve to None in tests). Settings' own env_file fallback
# (see app/core/config.py) would otherwise read the real .env directly
# for exactly that gap - confirmed empirically: a test asserting the
# "AI not configured" 503 path instead made a REAL Gemini API call,
# because settings.gemini_api_key silently picked up the real key from
# .env. ENV_FILE redirects that same fallback mechanism at .env.test
# instead, closing the leak for this and any future optional setting,
# not just the two AI keys.
os.environ["ENV_FILE"] = str(_ENV_TEST_PATH)

from app.db.session import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.reference_data.seed import seed_all  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """app is a single module-level instance imported once for the whole
    test session (see the `client` fixture below), so slowapi's in-memory
    hit counters (app/core/rate_limit.py) would otherwise accumulate
    across every test that touches a rate-limited route - a test file
    with more login/register calls than the real per-minute limit would
    start failing on unrelated assertions, not the rate limiting itself.
    Resetting before every test keeps each test's view of the limiter
    empty, while still letting a dedicated test intentionally exceed a
    limit within its own function body to prove the 429 path fires for
    real (see test_auth_api.py/test_ai_api.py's own rate-limit tests).
    """
    app.state.limiter.reset()


@pytest.fixture(scope="session", autouse=True)
def _seed_reference_data() -> None:
    """Ensure reference/taxonomy data exists before any test runs.

    seed_all() upserts by natural key, so this is safe to run once per
    test session even if something else also seeds compintel_test
    separately (e.g. a future CI step) - never duplicates.
    """
    with SessionLocal() as session:
        seed_all(session)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def unreachable_db_client() -> Generator[TestClient, None, None]:
    """Client whose DB dependency points at an unreachable address.

    Exercises the readiness check's failure path for real (a genuine failed
    connection attempt) without needing to take down compintel_test.
    """
    broken_engine = create_engine("postgresql+psycopg://invalid:invalid@127.0.0.1:1/nonexistent")
    broken_session_factory = sessionmaker(bind=broken_engine)

    def broken_get_db() -> Generator[Session, None, None]:
        db = broken_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = broken_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
