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
load_dotenv(Path(__file__).resolve().parent.parent / ".env.test", override=True)

from app.db.session import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.reference_data.seed import seed_all  # noqa: E402


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
