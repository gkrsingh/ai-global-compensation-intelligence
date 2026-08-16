from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.comparison.models import Comparison, ComparisonCalculation
from app.comparison.orchestration import UnknownCalculationError, build_comparison
from app.comparison.schemas import (
    ComparisonCreate,
    ComparisonDetailOut,
    ComparisonSummaryOut,
    PaginatedComparisonsOut,
)
from app.compensation.schemas import CalculationOut
from app.compensation.services.currency import MissingExchangeRateError
from app.core.exceptions import AppError
from app.db.session import get_db
from app.reference_data.models import Currency

router = APIRouter()


def _get_currency(db: Session, code: str) -> Currency:
    # Mirrors compensation/api.py's _get_currency exactly - same code,
    # same message shape - so an unknown comparison currency reads
    # identically to an unknown calculation currency anywhere else in
    # this API.
    currency = db.scalar(select(Currency).where(Currency.code == code.upper()))
    if currency is None:
        raise AppError(f"Unknown currency code: {code}", code="unknown_currency", status_code=404)
    return currency


def _comparison_not_found() -> AppError:
    return AppError("Comparison not found", code="comparison_not_found", status_code=404)


def _load_for_detail(db: Session, comparison_id: int) -> Comparison | None:
    return db.scalar(
        select(Comparison)
        .where(Comparison.id == comparison_id)
        .options(
            selectinload(Comparison.comparison_currency),
            selectinload(Comparison.items).selectinload(ComparisonCalculation.calculation),
        )
    )


def _to_detail_out(comparison: Comparison) -> ComparisonDetailOut:
    result: dict[str, Any] = comparison.result
    calculations_by_id = {item.calculation_id: item.calculation for item in comparison.items}
    ordered_calculation_ids = [item.calculation_id for item in comparison.items]

    return ComparisonDetailOut(
        id=comparison.id,
        name=comparison.name,
        comparison_currency=comparison.comparison_currency.code,
        as_of_date=comparison.as_of_date,
        created_at=comparison.created_at,
        entries=result["entries"],
        gap_analysis=result["gap_analysis"],
        calculations=[
            CalculationOut.model_validate(calculations_by_id[calc_id])
            for calc_id in ordered_calculation_ids
        ],
    )


@router.post(
    "/comparisons", response_model=ComparisonDetailOut, status_code=status.HTTP_201_CREATED
)
def create_comparison(
    payload: ComparisonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonDetailOut:
    """Auth is always required - unlike POST /calculations, there is no
    anonymous equivalent: a comparison inherently operates on saved
    history, which anonymous use doesn't have.
    """
    currency = _get_currency(db, payload.comparison_currency_code)

    try:
        comparison = build_comparison(
            db,
            current_user,
            payload.name,
            payload.calculation_ids,
            currency.code,
            payload.as_of_date or date.today(),
        )
    except UnknownCalculationError as exc:
        raise _comparison_not_found() from exc
    except MissingExchangeRateError as exc:
        raise AppError(
            f"No exchange rate available for {exc.from_currency} -> {exc.to_currency}",
            code="missing_exchange_rate",
            status_code=422,
        ) from exc

    db.commit()
    # Reload with the same eager-loading GET uses, rather than trying to
    # refresh individual relationships piecemeal post-commit.
    persisted = _load_for_detail(db, comparison.id)
    assert persisted is not None, "just committed - must be loadable by its own id"
    return _to_detail_out(persisted)


@router.get("/comparisons/mine", response_model=PaginatedComparisonsOut)
def list_my_comparisons(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedComparisonsOut:
    base_query = select(Comparison).where(Comparison.user_id == current_user.id)

    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    items = db.scalars(
        base_query.options(
            selectinload(Comparison.comparison_currency), selectinload(Comparison.items)
        )
        .order_by(Comparison.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return PaginatedComparisonsOut(
        items=[
            ComparisonSummaryOut(
                id=c.id,
                name=c.name,
                comparison_currency=c.comparison_currency.code,
                as_of_date=c.as_of_date,
                created_at=c.created_at,
                calculation_count=len(c.items),
            )
            for c in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDetailOut)
def get_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonDetailOut:
    """Scoped to the caller's own comparisons only - a comparison_id
    belonging to another user returns the same 404 as one that doesn't
    exist at all (see UnknownCalculationError's docstring for the same
    enumeration-avoidance reasoning applied here at the read side).
    """
    comparison = _load_for_detail(db, comparison_id)
    if comparison is None or comparison.user_id != current_user.id:
        raise _comparison_not_found()

    return _to_detail_out(comparison)
