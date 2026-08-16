from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.orchestration import (
    InsightGenerationFailedError,
    UnknownInsightTargetError,
    get_or_generate_insight,
)
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import AIProvider, AIProviderError
from app.ai.schemas import AIInsightCreate, AIInsightOut
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import get_db

router = APIRouter()


def get_ai_provider() -> AIProvider:
    """A FastAPI dependency (not a plain module-level call) specifically
    so tests can override it via app.dependency_overrides - the same
    pattern conftest.py's unreachable_db_client fixture already
    established for get_db. Lets API-level tests exercise the real
    endpoint and orchestration code against a stub provider, with zero
    risk of ever making a live call to the real Anthropic API.
    """
    if settings.anthropic_api_key is None:
        raise AppError(
            "AI insight is not configured on this server",
            code="ai_not_configured",
            status_code=503,
        )
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_model)


def _insight_target_not_found() -> AppError:
    return AppError(
        "Calculation or comparison not found", code="insight_target_not_found", status_code=404
    )


@router.post("/ai-insights", response_model=AIInsightOut)
def create_or_get_insight(
    payload: AIInsightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
) -> AIInsightOut:
    """Auth is always required - like Phase 7's comparisons, AI insight
    has no anonymous equivalent: it costs real money per call and needs
    a real identity to attach accountability to.

    Deliberately idempotent-safe despite being a POST: a repeated call
    for the same target returns the same cached, already-passed result
    rather than generating (and re-billing) again - see
    get_or_generate_insight's own caching logic. 200, not 201, for this
    reason - a cache hit genuinely isn't "creating" anything, and the
    caller shouldn't need to care which happened.
    """
    try:
        outcome = get_or_generate_insight(
            db,
            current_user,
            provider,
            calculation_id=payload.calculation_id,
            comparison_id=payload.comparison_id,
        )
    except UnknownInsightTargetError as exc:
        raise _insight_target_not_found() from exc
    except InsightGenerationFailedError as exc:
        # The failed attempts ARE persisted - the whole point of this
        # being a real audit trail rather than a log line - so commit
        # them even though this call itself reports failure.
        db.commit()
        raise AppError(
            "AI insight could not be generated for this item right now. Please try again later.",
            code="ai_insight_unavailable",
            status_code=422,
        ) from exc
    except AIProviderError as exc:
        db.commit()
        raise AppError(
            "The AI service is temporarily unavailable. Please try again later.",
            code="ai_provider_unavailable",
            status_code=502,
        ) from exc

    db.commit()
    db.refresh(outcome.result)
    return AIInsightOut(
        id=outcome.result.id,
        request_id=outcome.request.id,
        calculation_id=outcome.request.calculation_id,
        comparison_id=outcome.request.comparison_id,
        provider=outcome.result.provider,
        model=outcome.result.model,
        generated_text=outcome.result.generated_text,
        created_at=outcome.result.created_at,
        cached=outcome.cached,
    )
