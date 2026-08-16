"""DB-touching orchestration for building a Comparison: loads the
referenced Calculations and exchange rates, then delegates the actual
normalization math to the pure services/normalize.py - the same
db-touches-here / math-lives-there split as compensation/engine.py.

Per the phase's hard constraint, this NEVER re-runs the calculation
engine or recomputes tax: each Calculation's gross/total/tax/net figures
are loaded as-is and only ever currency-converted for display.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.models import User
from app.comparison.models import Comparison, ComparisonCalculation
from app.comparison.services.normalize import (
    CalculationSnapshot,
    ComparisonResult,
    normalize_and_compare,
)
from app.compensation.models import Calculation, CompensationInput
from app.compensation.repositories import build_rates
from app.reference_data.models import Currency


class UnknownCalculationError(Exception):
    """One or more requested calculation_ids don't exist, or exist but
    belong to a different user. Deliberately a single error covering both
    cases with no way to tell them apart from the outside - the API layer
    turns this into a 404, the same "don't confirm what you can't see"
    choice already established for login/refresh (see
    app/auth/dependencies.py's docstring): a 403 here would confirm to a
    caller that a given calculation_id exists and belongs to someone else,
    which is exactly the kind of enumeration leak that precedent exists
    to avoid.
    """

    def __init__(self, calculation_ids: set[int]) -> None:
        self.calculation_ids = calculation_ids
        super().__init__(f"Unknown calculation id(s): {sorted(calculation_ids)}")


def _load_owned_calculations(
    session: Session, user: User, calculation_ids: list[int]
) -> dict[int, Calculation]:
    rows = list(
        session.scalars(
            select(Calculation)
            .where(Calculation.id.in_(calculation_ids), Calculation.user_id == user.id)
            .options(
                selectinload(Calculation.compensation_input).selectinload(
                    CompensationInput.target_currency
                )
            )
        )
    )
    found = {c.id: c for c in rows}
    missing = set(calculation_ids) - found.keys()
    if missing:
        raise UnknownCalculationError(missing)
    return found


def _get_currency(session: Session, code: str) -> Currency | None:
    return session.scalar(select(Currency).where(Currency.code == code))


def _serialize_result(result: ComparisonResult) -> dict[str, object]:
    def _dec(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    return {
        "comparison_currency": result.comparison_currency,
        "entries": [
            {
                "calculation_id": e.calculation_id,
                "source_currency": e.source_currency,
                "rate_used": _dec(e.rate_used),
                "gross_amount": _dec(e.gross_amount),
                "total_compensation_amount": _dec(e.total_compensation_amount),
                "total_tax_amount": _dec(e.total_tax_amount),
                "net_amount": _dec(e.net_amount),
            }
            for e in result.entries
        ],
        "gap_analysis": {
            metric: (
                None
                if gap is None
                else {
                    "leader_calculation_id": gap.leader_calculation_id,
                    "entries": [
                        {
                            "calculation_id": g.calculation_id,
                            "gap_absolute": _dec(g.gap_absolute),
                            "gap_percent": _dec(g.gap_percent),
                        }
                        for g in gap.entries
                    ],
                }
            )
            for metric, gap in result.gap_analysis.items()
        },
    }


def build_comparison(
    session: Session,
    user: User,
    name: str,
    calculation_ids: list[int],
    comparison_currency_code: str,
    as_of: date,
) -> Comparison:
    """Stages (session.add) but does not commit - committing is the
    caller's job, consistent with every other orchestration function in
    this project (run_calculation, fetch_and_persist).

    Raises UnknownCalculationError (missing or not-owned calculation id)
    or MissingExchangeRateError (compensation.services.currency) - both
    left uncaught here for the API layer to translate, same pattern as
    run_calculation's MissingExchangeRateError/AmbiguousTaxRuleSetError.
    """
    owned = _load_owned_calculations(session, user, calculation_ids)

    snapshots = [
        CalculationSnapshot(
            calculation_id=calc_id,
            source_currency=owned[calc_id].compensation_input.target_currency.code,
            gross_amount=owned[calc_id].gross_amount,
            total_compensation_amount=owned[calc_id].total_compensation_amount,
            total_tax_amount=owned[calc_id].total_tax_amount,
            net_amount=owned[calc_id].net_amount,
        )
        for calc_id in calculation_ids
    ]

    source_currencies = {s.source_currency for s in snapshots}
    rates = build_rates(session, source_currencies, comparison_currency_code, as_of)

    result = normalize_and_compare(snapshots, comparison_currency_code, rates)

    currency = _get_currency(session, comparison_currency_code)
    assert currency is not None, "caller must validate comparison_currency_code before this point"

    comparison = Comparison(
        user_id=user.id,
        name=name,
        comparison_currency_id=currency.id,
        as_of_date=as_of,
        result=_serialize_result(result),
    )
    comparison.items = [
        ComparisonCalculation(calculation_id=calc_id, position=position)
        for position, calc_id in enumerate(calculation_ids)
    ]
    session.add(comparison)
    return comparison
