"""Read-only queries over reference/taxonomy data.

Deliberately not calculation logic — row selection only. The calculation
engine (Phase 3) and the read-only API (Phase 2 step 6) both need "find
the currently-effective tax rule set" as a building block; this is that
building block, written once.
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import Session

from app.reference_data.models import Country, TaxRuleSet


class AmbiguousTaxRuleSetError(Exception):
    """Raised when more than one TaxRuleSet matches a query that didn't
    narrow by regime/filing_status enough to pick just one - e.g. India
    has separate old/new-regime rule sets both effective today, so asking
    for "IN as of today" with no regime is genuinely ambiguous, not a bug
    in the data. Discovered via the Phase 4 UI, which (correctly) doesn't
    force a regime choice up front - the very first real caller to hit
    this path without pre-selecting one.
    """

    def __init__(self, country_code: str, as_of: date) -> None:
        self.country_code = country_code
        self.as_of = as_of
        super().__init__(
            f"Multiple tax rule sets apply for {country_code} as of {as_of}; "
            "specify a regime and/or filing_status to disambiguate."
        )


def get_effective_tax_rule_set(
    session: Session,
    country_code: str,
    as_of: date,
    regime: str | None = None,
    filing_status: str | None = None,
) -> TaxRuleSet | None:
    """The TaxRuleSet for a country whose [effective_date, end_date] covers
    as_of, optionally narrowed by regime/filing_status. None if no rule
    set covers that date. Raises AmbiguousTaxRuleSetError if more than one
    still matches - callers should treat that as something the caller
    needs to disambiguate, not something to silently pick one of.
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
    try:
        return session.execute(stmt).scalar_one_or_none()
    except MultipleResultsFound as exc:
        raise AmbiguousTaxRuleSetError(country_code, as_of) from exc
