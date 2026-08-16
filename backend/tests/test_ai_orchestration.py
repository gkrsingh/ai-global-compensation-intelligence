"""Tests for get_or_generate_insight - the actual wiring between the
provider, the prompts, and the numeric-consistency checker. Uses a stub
AIProvider (never a real anthropic.Anthropic call) so these can exercise
the full orchestration logic - caching, retry-on-failure, the
regeneration-prompt laundering guard - deterministically and for free.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AIAnalysisRequest, AIAnalysisResult
from app.ai.orchestration import (
    InsightGenerationFailedError,
    UnknownInsightTargetError,
    get_or_generate_insight,
)
from app.ai.providers.base import AIProvider, GeneratedText
from app.auth.models import User
from app.comparison.orchestration import build_comparison
from app.compensation.engine import run_calculation
from app.compensation.models import (
    Calculation,
    CompensationComponent,
    CompensationInput,
    ComponentType,
)
from app.reference_data.models import Country, Currency


class _StubProvider(AIProvider):
    """Returns canned responses in order, one per call; the last
    response repeats if generate() is called more times than there are
    canned responses. Tracks every prompt it was actually called with,
    so tests can assert on exactly what the orchestration layer sent.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.call_count = 0
        self.received_user_prompts: list[str] = []

    @property
    def name(self) -> str:
        return "stub"

    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        self.call_count += 1
        self.received_user_prompts.append(user_prompt)
        index = min(self.call_count - 1, len(self._responses) - 1)
        return GeneratedText(text=self._responses[index], model="stub-model-v1")


def _user(db_session: Session, email: str) -> User:
    user = User(email=email, hashed_password="x")
    db_session.add(user)
    db_session.flush()
    return user


def _owned_calculation(db_session: Session, user: User) -> Calculation:
    us = db_session.scalar(select(Country).where(Country.code == "US"))
    usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
    assert us is not None and usd is not None
    comp_input = CompensationInput(
        country_id=us.id, target_currency_id=usd.id, filing_status="single", as_of_date=date.today()
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("150000.00"), currency_id=usd.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()
    calculation.user_id = user.id
    db_session.flush()
    return calculation


def test_generates_and_persists_a_passing_insight(db_session: Session) -> None:
    user = _user(db_session, "ai-orch-1@example.com")
    calculation = _owned_calculation(db_session, user)
    provider = _StubProvider(
        ["This offer has a gross of $150,000.00 and a net of $113,791.00."]
    )

    outcome = get_or_generate_insight(
        db_session, user, provider, calculation_id=calculation.id, comparison_id=None
    )
    db_session.flush()

    assert outcome.cached is False
    assert outcome.result.consistency_check_passed is True
    assert provider.call_count == 1

    persisted = db_session.get(AIAnalysisResult, outcome.result.id)
    assert persisted is not None
    assert persisted.generated_text == outcome.result.generated_text
    assert persisted.provider == "stub"
    assert persisted.model == "stub-model-v1"


def test_second_call_returns_the_cached_result_without_calling_the_provider_again(
    db_session: Session,
) -> None:
    user = _user(db_session, "ai-orch-2@example.com")
    calculation = _owned_calculation(db_session, user)
    provider = _StubProvider(["Gross is $150,000.00, net is $113,791.00."])

    first = get_or_generate_insight(
        db_session, user, provider, calculation_id=calculation.id, comparison_id=None
    )
    db_session.flush()
    assert provider.call_count == 1

    second = get_or_generate_insight(
        db_session, user, provider, calculation_id=calculation.id, comparison_id=None
    )

    assert second.cached is True
    assert second.result.id == first.result.id
    assert provider.call_count == 1  # unchanged - no new provider call


def test_a_failed_first_attempt_regenerates_and_succeeds_on_the_second(
    db_session: Session,
) -> None:
    user = _user(db_session, "ai-orch-3@example.com")
    calculation = _owned_calculation(db_session, user)
    provider = _StubProvider(
        [
            "This is comfortably above the market average of $999,999.00.",  # fabricated
            "Gross is $150,000.00, net is $113,791.00.",  # clean
        ]
    )

    outcome = get_or_generate_insight(
        db_session, user, provider, calculation_id=calculation.id, comparison_id=None
    )
    db_session.flush()

    assert provider.call_count == 2
    assert outcome.cached is False
    assert outcome.result.consistency_check_passed is True
    assert "150,000" in outcome.result.generated_text

    # The regeneration prompt must mention the earlier fabricated number
    # (to help the model self-correct)...
    assert "999999.00" in provider.received_user_prompts[1]
    # ...but the SECOND attempt's own consistency check must still be
    # evaluated against the ORIGINAL grounded data, not that note - if
    # it weren't, a second attempt that repeated the SAME fabricated
    # number would incorrectly pass, since the note text itself now
    # "contains" that number. Proven directly in the dedicated test
    # below, not just asserted here.

    request = db_session.get(AIAnalysisRequest, outcome.request.id)
    assert request is not None
    assert len(request.results) == 2
    assert request.results[0].consistency_check_passed is False
    assert request.results[1].consistency_check_passed is True


def test_the_regeneration_notes_own_mention_of_the_bad_number_does_not_launder_it(
    db_session: Session,
) -> None:
    """The critical guard: if the SECOND attempt repeats the exact same
    fabricated number the regeneration note warned about, it must still
    fail - the note text mentioning that number (to help the model avoid
    it) must never be mistaken for grounded data by the checker.
    """
    user = _user(db_session, "ai-orch-4@example.com")
    calculation = _owned_calculation(db_session, user)
    provider = _StubProvider(
        [
            "Comfortably above the market average of $999,999.00.",
            "Still comfortably above the market average of $999,999.00.",  # repeats the mistake
        ]
    )

    with pytest.raises(InsightGenerationFailedError):
        get_or_generate_insight(
            db_session, user, provider, calculation_id=calculation.id, comparison_id=None
        )
    db_session.flush()

    assert provider.call_count == 2


def test_exhausting_all_attempts_persists_every_failed_result(db_session: Session) -> None:
    user = _user(db_session, "ai-orch-5@example.com")
    calculation = _owned_calculation(db_session, user)
    provider = _StubProvider(
        [
            "Fabricated figure one: $111,111.00.",
            "Fabricated figure two: $222,222.00.",
        ]
    )

    with pytest.raises(InsightGenerationFailedError):
        get_or_generate_insight(
            db_session, user, provider, calculation_id=calculation.id, comparison_id=None
        )
    db_session.flush()

    requests = db_session.scalars(
        select(AIAnalysisRequest).where(
            AIAnalysisRequest.user_id == user.id, AIAnalysisRequest.calculation_id == calculation.id
        )
    ).all()
    assert len(requests) == 1
    results = requests[0].results
    assert len(results) == 2
    assert all(r.consistency_check_passed is False for r in results)
    assert {r.generated_text for r in results} == {
        "Fabricated figure one: $111,111.00.",
        "Fabricated figure two: $222,222.00.",
    }


def test_referencing_someone_elses_calculation_raises_unknown_target(db_session: Session) -> None:
    owner = _user(db_session, "ai-orch-owner@example.com")
    other = _user(db_session, "ai-orch-other@example.com")
    calculation = _owned_calculation(db_session, owner)
    provider = _StubProvider(["should never be called"])

    with pytest.raises(UnknownInsightTargetError):
        get_or_generate_insight(
            db_session, other, provider, calculation_id=calculation.id, comparison_id=None
        )

    assert provider.call_count == 0


def test_referencing_a_nonexistent_calculation_raises_unknown_target(db_session: Session) -> None:
    user = _user(db_session, "ai-orch-6@example.com")
    provider = _StubProvider(["should never be called"])

    with pytest.raises(UnknownInsightTargetError):
        get_or_generate_insight(
            db_session, user, provider, calculation_id=999999999, comparison_id=None
        )

    assert provider.call_count == 0


def test_referencing_someone_elses_comparison_raises_unknown_target(db_session: Session) -> None:
    owner = _user(db_session, "ai-orch-comp-owner@example.com")
    other = _user(db_session, "ai-orch-comp-other@example.com")
    calc_a = _owned_calculation(db_session, owner)
    calc_b = _owned_calculation(db_session, owner)
    comparison = build_comparison(
        db_session, owner, "ownership test", [calc_a.id, calc_b.id], "USD", date.today()
    )
    db_session.flush()
    provider = _StubProvider(["should never be called"])

    with pytest.raises(UnknownInsightTargetError):
        get_or_generate_insight(
            db_session, other, provider, calculation_id=None, comparison_id=comparison.id
        )

    assert provider.call_count == 0
