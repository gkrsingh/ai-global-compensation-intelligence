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


# Real May 2025 OEWS figures, captured from actual BLS API responses
# during Phase 10 research and reused verbatim as fixture data. Using the
# real numbers (rather than round invented ones) keeps the fixtures
# recognisable against the live source, and driving them through the real
# ingestion code path exercises that code too - while the automated suite
# still never makes a live call.
#
# Codes with only a median are the ones whose full distribution was not
# captured; they double as honest coverage of the partial-data path,
# where a source publishes some figures and not others.
_REAL_OEWS_MAY_2025: dict[str, dict[str, str | int]] = {
    "151252": {
        "p10": "82460", "p25": "105210", "p50": "135980",
        "p75": "171980", "p90": "214670", "mean": "148100", "emp": 1687890,
    },
    "152051": {
        "p10": "67240", "p25": "85660", "p50": "120230",
        "p75": "158880", "p90": "199130", "mean": "126800", "emp": 262440,
    },
    "131082": {
        "p10": "61580", "p25": "78440", "p50": "102320",
        "p75": "133100", "p90": "167970", "mean": "110740", "emp": 1066670,
    },
    "151253": {"p50": "104300"},
    "152041": {"p50": "105650"},
    "151255": {"p50": "104000"},
    "271024": {"p50": "62960"},
    "413091": {"p50": "69990"},
    "112022": {"p50": "148270"},
}


@pytest.fixture()
def ingested_market_data(db_session: Session) -> None:
    """Persists the real captured OEWS vintage into the test DB by
    running the actual ingestion function against a stub provider.

    Idempotent (fetch_and_persist upserts by natural key), so repeated
    use across tests neither duplicates rows nor needs teardown - the
    same treatment tax brackets and currencies already get from
    seed_all.
    """
    from decimal import Decimal

    from app.market_data.ingest import fetch_and_persist
    from app.market_data.providers.base import MarketDataProvider, OccupationWages

    class _StubOewsProvider(MarketDataProvider):
        @property
        def name(self) -> str:
            return "stub_oews"

        @property
        def taxonomy(self) -> str:
            return "SOC-2018"

        def fetch_national_wages(self, external_code: str) -> OccupationWages:
            figures = _REAL_OEWS_MAY_2025.get(external_code, {})

            def _dec(key: str) -> Decimal | None:
                raw = figures.get(key)
                return Decimal(str(raw)) if raw is not None else None

            employment = figures.get("emp")
            return OccupationWages(
                external_code=external_code,
                external_label=None,
                reference_year=2025,
                percentile_10=_dec("p10"),
                percentile_25=_dec("p25"),
                percentile_50=_dec("p50"),
                percentile_75=_dec("p75"),
                percentile_90=_dec("p90"),
                mean_value=_dec("mean"),
                employment_count=int(employment) if employment is not None else None,
            )

    fetch_and_persist(db_session, _StubOewsProvider())
    db_session.commit()


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
