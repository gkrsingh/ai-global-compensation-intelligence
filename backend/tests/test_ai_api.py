"""Integration tests for POST /ai-insights - the full HTTP stack (auth ->
ownership -> orchestration -> provider -> consistency check ->
persistence -> response), same style as test_comparison_api.py. The
Anthropic provider is swapped for a stub via FastAPI's own
dependency_overrides (app.ai.api.get_ai_provider), so these exercise the
real endpoint and orchestration code with zero risk of ever calling the
real API - the same guarantee test_ai_provider.py's httpx.MockTransport
gives at the adapter layer, applied here at the whole-request layer.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.api import get_ai_provider
from app.ai.models import AIAnalysisRequest, AIAnalysisResult
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import AIProvider, AIProviderError, GeneratedText
from app.auth.models import User
from app.compensation.models import Calculation
from app.core.config import settings
from app.main import app


class _StubProvider(AIProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.call_count = 0

    @property
    def name(self) -> str:
        return "stub"

    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        self.call_count += 1
        index = min(self.call_count - 1, len(self.responses) - 1)
        return GeneratedText(text=self.responses[index], model="stub-model-v1")


class _FailingProvider(AIProvider):
    @property
    def name(self) -> str:
        return "stub"

    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        raise AIProviderError("simulated provider outage")


@pytest.fixture()
def stub_provider() -> Generator[_StubProvider, None, None]:
    provider = _StubProvider(["Gross is $150,000.00, net is $113,791.00."])
    app.dependency_overrides[get_ai_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_ai_provider, None)


def _register_and_login(client: TestClient, email: str) -> str:
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    access_token: str = login.json()["access_token"]
    return access_token


def _create_calculation(client: TestClient, token: str, amount: str = "150000.00") -> int:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "filing_status": "single",
            "target_currency_code": "USD",
            "components": [{"component_type": "base", "amount": amount, "currency_code": "USD"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.json()
    calculation_id: int = response.json()["id"]
    return calculation_id


def _cleanup_ai_requests(db_session: Session, *, calculation_id: int | None = None,
                          comparison_id: int | None = None) -> None:
    # ORM-level delete (not raw SQL) so AIAnalysisRequest.results'
    # cascade="all, delete-orphan" actually fires and removes the
    # associated AIAnalysisResult rows too.
    stmt = select(AIAnalysisRequest)
    if calculation_id is not None:
        stmt = stmt.where(AIAnalysisRequest.calculation_id == calculation_id)
    if comparison_id is not None:
        stmt = stmt.where(AIAnalysisRequest.comparison_id == comparison_id)
    for request in db_session.scalars(stmt).all():
        db_session.delete(request)


def _cleanup_calculations(db_session: Session, calculation_ids: list[int]) -> None:
    for calc_id in calculation_ids:
        calc = db_session.get(Calculation, calc_id)
        if calc is not None:
            comp_input = calc.compensation_input
            _cleanup_ai_requests(db_session, calculation_id=calc_id)
            db_session.delete(calc)
            db_session.delete(comp_input)
    db_session.commit()


def _cleanup_user(db_session: Session, email: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    if user is not None:
        db_session.delete(user)
        db_session.commit()


def test_get_ai_provider_constructs_a_real_provider_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The successful branch of get_ai_provider() - never exercised by
    any HTTP test above, since those either override the dependency or
    rely on the (always-unset-in-test-env) real key being absent to
    prove the 503 path. Merely constructing AnthropicProvider makes no
    network call (only .generate() would), so this is safe to test
    directly without touching the real API.
    """
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-construction-only")

    provider = get_ai_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"


def test_create_insight_returns_generated_text_and_persists(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email = "ai-api-1@example.com"
    token = _register_and_login(client, email)
    calc_id = _create_calculation(client, token)

    response = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": calc_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["generated_text"] == "Gross is $150,000.00, net is $113,791.00."
    assert body["provider"] == "stub"
    assert body["model"] == "stub-model-v1"
    assert body["cached"] is False
    assert body["calculation_id"] == calc_id
    assert body["comparison_id"] is None

    persisted = db_session.get(AIAnalysisResult, body["id"])
    assert persisted is not None
    assert persisted.consistency_check_passed is True

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email)


def test_second_request_is_served_from_cache_without_calling_the_provider_again(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email = "ai-api-2@example.com"
    token = _register_and_login(client, email)
    calc_id = _create_calculation(client, token)

    first = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": calc_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert stub_provider.call_count == 1

    second = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": calc_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["id"] == first.json()["id"]
    assert stub_provider.call_count == 1  # unchanged

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email)


def test_create_insight_requires_authentication(
    client: TestClient, stub_provider: _StubProvider
) -> None:
    response = client.post("/api/v1/ai-insights", json={"calculation_id": 1})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert stub_provider.call_count == 0


def test_create_insight_rejects_someone_elses_calculation(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email_a = "ai-api-owner@example.com"
    email_b = "ai-api-other@example.com"
    token_a = _register_and_login(client, email_a)
    token_b = _register_and_login(client, email_b)
    calc_id = _create_calculation(client, token_a)

    response = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": calc_id},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Uniform 404, not 403 - same enumeration-avoidance reasoning as
    # comparison_not_found in Phase 7.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "insight_target_not_found"
    assert stub_provider.call_count == 0

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email_a)
    _cleanup_user(db_session, email_b)


def test_create_insight_rejects_a_nonexistent_calculation(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email = "ai-api-3@example.com"
    token = _register_and_login(client, email)

    response = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": 999999999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "insight_target_not_found"

    _cleanup_user(db_session, email)


def test_create_insight_requires_exactly_one_target(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email = "ai-api-4@example.com"
    token = _register_and_login(client, email)

    neither = client.post(
        "/api/v1/ai-insights", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    assert neither.status_code == 422

    both = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": 1, "comparison_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert both.status_code == 422

    _cleanup_user(db_session, email)


def test_create_insight_returns_422_when_every_attempt_fails_the_consistency_check(
    client: TestClient, db_session: Session
) -> None:
    email = "ai-api-5@example.com"
    token = _register_and_login(client, email)
    calc_id = _create_calculation(client, token)

    provider = _StubProvider(
        [
            "Fabricated: $111,111.00.",
            "Also fabricated: $222,222.00.",
        ]
    )
    app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = client.post(
            "/api/v1/ai-insights",
            json={"calculation_id": calc_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ai_insight_unavailable"
    assert provider.call_count == 2

    # Both failed attempts are still persisted - the whole point of the
    # audit trail this phase's safeguard depends on.
    requests = db_session.scalars(
        select(AIAnalysisRequest).where(AIAnalysisRequest.calculation_id == calc_id)
    ).all()
    assert len(requests) == 1
    assert len(requests[0].results) == 2
    assert all(r.consistency_check_passed is False for r in requests[0].results)

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email)


def test_create_insight_returns_502_when_the_provider_itself_fails(
    client: TestClient, db_session: Session
) -> None:
    email = "ai-api-6@example.com"
    token = _register_and_login(client, email)
    calc_id = _create_calculation(client, token)

    app.dependency_overrides[get_ai_provider] = lambda: _FailingProvider()
    try:
        response = client.post(
            "/api/v1/ai-insights",
            json={"calculation_id": calc_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_provider_unavailable"

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email)


def test_create_insight_returns_503_when_ai_is_not_configured(
    client: TestClient, db_session: Session
) -> None:
    """The REAL get_ai_provider dependency, not overridden - proves the
    actual production code path (ANTHROPIC_API_KEY unset, which it
    always is in this test environment) fails gracefully rather than
    the whole app breaking.
    """
    email = "ai-api-7@example.com"
    token = _register_and_login(client, email)
    calc_id = _create_calculation(client, token)

    response = client.post(
        "/api/v1/ai-insights",
        json={"calculation_id": calc_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"

    _cleanup_calculations(db_session, [calc_id])
    _cleanup_user(db_session, email)


def test_create_insight_for_a_comparison(
    client: TestClient, db_session: Session, stub_provider: _StubProvider
) -> None:
    email = "ai-api-8@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")
    calc_b = _create_calculation(client, token, "100000.00")

    comparison = client.post(
        "/api/v1/comparisons",
        json={
            "name": "AI insight comparison test",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    response = client.post(
        "/api/v1/ai-insights",
        json={"comparison_id": comparison["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["comparison_id"] == comparison["id"]
    assert body["calculation_id"] is None
    assert stub_provider.call_count == 1

    from app.comparison.models import Comparison

    db_comparison = db_session.get(Comparison, comparison["id"])
    assert db_comparison is not None
    _cleanup_ai_requests(db_session, comparison_id=comparison["id"])
    db_session.delete(db_comparison)
    db_session.commit()
    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email)
