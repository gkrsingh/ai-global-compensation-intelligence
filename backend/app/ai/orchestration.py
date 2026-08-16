"""DB-touching orchestration for generating (or returning cached) AI
insight: loads the target, enforces ownership, checks the cache, calls
the provider, runs the numeric-consistency check, and persists the full
audit trail. Mirrors comparison/orchestration.py's layering - I/O and DB
access here, pure math/logic in app/ai/prompts/ and
app/ai/services/consistency.py.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AIAnalysisRequest, AIAnalysisResult
from app.ai.prompts.calculation import build_calculation_context, render_calculation_prompt
from app.ai.prompts.comparison import build_comparison_context, render_comparison_prompt
from app.ai.prompts.system import SYSTEM_PROMPT
from app.ai.providers.base import AIProvider
from app.ai.services.consistency import ConsistencyCheckResult, check_numeric_consistency
from app.auth.models import User
from app.comparison.models import Comparison
from app.compensation.models import Calculation

# One generation + one regeneration if the first fails the numeric-
# consistency check. Real per-call cost (the phase's own emphasis) is
# why this is bounded rather than looped until it passes.
MAX_ATTEMPTS = 2


class UnknownInsightTargetError(Exception):
    """The referenced calculation/comparison doesn't exist, or exists
    but isn't owned by the caller - deliberately a single error covering
    both cases, same enumeration-avoidance reasoning as
    UnknownCalculationError in comparison/orchestration.py: a caller
    should not be able to tell "doesn't exist" apart from "exists and
    belongs to someone else" from the outside.
    """


class InsightGenerationFailedError(Exception):
    """Every attempt (up to MAX_ATTEMPTS) failed the numeric-consistency
    check. The failures are still fully persisted (AIAnalysisResult rows
    with consistency_check_passed=False) - this just signals to the
    caller that there's no trustworthy text to return this time.
    """


@dataclass(frozen=True)
class InsightOutcome:
    request: AIAnalysisRequest
    result: AIAnalysisResult
    cached: bool


def _load_owned_calculation(session: Session, user: User, calculation_id: int) -> Calculation:
    calc = session.get(Calculation, calculation_id)
    if calc is None or calc.user_id != user.id:
        raise UnknownInsightTargetError(f"calculation {calculation_id}")
    return calc


def _load_owned_comparison(session: Session, user: User, comparison_id: int) -> Comparison:
    comp = session.get(Comparison, comparison_id)
    if comp is None or comp.user_id != user.id:
        raise UnknownInsightTargetError(f"comparison {comparison_id}")
    return comp


def _find_cached_passed_result(
    session: Session, user: User, *, calculation_id: int | None, comparison_id: int | None
) -> AIAnalysisResult | None:
    stmt = (
        select(AIAnalysisResult)
        .join(AIAnalysisRequest, AIAnalysisResult.request_id == AIAnalysisRequest.id)
        .where(
            AIAnalysisRequest.user_id == user.id,
            AIAnalysisRequest.calculation_id == calculation_id,
            AIAnalysisRequest.comparison_id == comparison_id,
            AIAnalysisResult.consistency_check_passed.is_(True),
        )
        .order_by(AIAnalysisResult.created_at.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def _regeneration_prompt(base_user_prompt: str, previous_check: ConsistencyCheckResult) -> str:
    """A previous attempt included at least one number not present in
    DATA - naming those specific numbers gives the model something
    concrete to self-correct against, rather than a blind identical
    retry. This note is appended ONLY to what's sent to the provider; it
    is NEVER used as the basis for checking that attempt's own output
    (see the caller below) - if it were, the note's own mention of the
    fabricated number would launder it into looking like real data on
    the very next check, defeating the whole safeguard.
    """
    unmatched = ", ".join(previous_check.unmatched_numbers)
    return (
        f"{base_user_prompt}\n\n"
        f"NOTE: A previous attempt at this task incorrectly stated the following number(s), "
        f"which do NOT appear anywhere in the DATA section above: {unmatched}. "
        f"Re-read the DATA section carefully and only state numbers that appear there verbatim."
    )


def get_or_generate_insight(
    session: Session,
    user: User,
    provider: AIProvider,
    *,
    calculation_id: int | None,
    comparison_id: int | None,
) -> InsightOutcome:
    """Stages (session.add) but does not commit - committing is the
    caller's job, consistent with every other orchestration function in
    this project (run_calculation, build_comparison).

    Raises UnknownInsightTargetError or InsightGenerationFailedError,
    left uncaught here for the API layer to translate - same pattern as
    run_calculation's MissingExchangeRateError. AIProviderError (a raw
    provider/network failure, distinct from a consistency-check failure)
    is also left uncaught, deliberately not retried the same way a
    consistency failure is: a transport-level failure is unlikely to be
    fixed by an identical immediate retry, unlike a semantic mistake a
    differently-worded second attempt has a real chance of avoiding.
    """
    if calculation_id is not None:
        _load_owned_calculation(session, user, calculation_id)
    else:
        assert comparison_id is not None
        _load_owned_comparison(session, user, comparison_id)

    cached = _find_cached_passed_result(
        session, user, calculation_id=calculation_id, comparison_id=comparison_id
    )
    if cached is not None:
        return InsightOutcome(request=cached.request, result=cached, cached=True)

    if calculation_id is not None:
        calculation = _load_owned_calculation(session, user, calculation_id)
        context = build_calculation_context(calculation)
        base_user_prompt = render_calculation_prompt(context)
    else:
        assert comparison_id is not None
        comparison = _load_owned_comparison(session, user, comparison_id)
        context = build_comparison_context(comparison)
        base_user_prompt = render_comparison_prompt(context)

    request = AIAnalysisRequest(
        user_id=user.id,
        calculation_id=calculation_id,
        comparison_id=comparison_id,
        context=context,
    )
    session.add(request)
    session.flush()

    prompt_to_send = base_user_prompt
    last_result: AIAnalysisResult | None = None

    for _attempt in range(MAX_ATTEMPTS):
        generated = provider.generate(system_prompt=SYSTEM_PROMPT, user_prompt=prompt_to_send)
        # ALWAYS checked against base_user_prompt's real numbers, never
        # prompt_to_send (which, on a retry, contains the previous
        # attempt's own fabricated number in its correction note - see
        # _regeneration_prompt's docstring for why that must never be
        # treated as grounded data).
        check = check_numeric_consistency(
            user_prompt=base_user_prompt, generated_text=generated.text
        )

        result = AIAnalysisResult(
            request_id=request.id,
            provider=provider.name,
            model=generated.model,
            prompt_text=prompt_to_send,
            generated_text=generated.text,
            consistency_check_passed=check.passed,
            consistency_check_details=check.to_details(),
        )
        session.add(result)
        session.flush()
        last_result = result

        if check.passed:
            return InsightOutcome(request=request, result=result, cached=False)

        prompt_to_send = _regeneration_prompt(base_user_prompt, check)

    assert last_result is not None
    raise InsightGenerationFailedError(
        f"Numeric consistency check failed after {MAX_ATTEMPTS} attempts "
        f"(request_id={request.id})"
    )
