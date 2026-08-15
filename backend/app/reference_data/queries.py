"""Read-only queries over reference/taxonomy data.

Deliberately not calculation logic — row selection only. The calculation
engine (Phase 3) and the read-only API (Phase 2 step 6) both need "find
the currently-effective tax rule set" as a building block; this is that
building block, written once.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.reference_data.models import Country, TaxRuleSet


def get_effective_tax_rule_set(
    session: Session,
    country_code: str,
    as_of: date,
    regime: str | None = None,
    filing_status: str | None = None,
) -> TaxRuleSet | None:
    """The TaxRuleSet for a country whose [effective_date, end_date] covers
    as_of, optionally narrowed by regime/filing_status. None if no rule
    set covers that date (or ambiguous, if more than one somehow does -
    callers should treat multiple future overlapping rule sets as a data
    problem, not something to silently pick one of).
    """
    stmt = (
        select(TaxRuleSet)
        .join(Country)
        .where(
            Country.code == country_code,
            TaxRuleSet.effective_date <= as_of,
            or_(TaxRuleSet.end_date.is_(None), TaxRuleSet.end_date >= as_of),
        )
    )
    if regime is not None:
        stmt = stmt.where(TaxRuleSet.regime == regime)
    if filing_status is not None:
        stmt = stmt.where(TaxRuleSet.filing_status == filing_status)
    return session.execute(stmt).scalar_one_or_none()
