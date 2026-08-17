"""Fetches published market wage data from a MarketDataProvider and
persists it as MarketDataPoint rows.

Run via `python -m app.market_data.ingest`.

Only occupations this project has actually mapped are fetched (see
market_data/seed.py) - there is no reason to ingest all 1,104 SOC
occupations when nine of them are reachable from the UI.

Idempotent like seed.py and fetch_exchange_rates.py: each row is upserted
by its natural key (country, taxonomy, occupation, area, reference
period), so re-running for the same vintage updates in place, while a new
vintage inserts new rows and leaves the previous ones as history.

Source-level metadata lives HERE rather than in the provider: the wage
definition and methodology are properties of the survey, cited once and
attached at ingestion, rather than something an adapter makes up per
request.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.market_data.models import (
    GeographicScope,
    JobFamilyOccupationMapping,
    MarketDataPoint,
)
from app.market_data.providers.base import MarketDataProvider
from app.market_data.providers.bls_oews import BlsOewsProvider
from app.reference_data.models import Country, Currency
from app.reference_data.upsert import upsert as _upsert

logger = logging.getLogger(__name__)

OEWS_SOURCE_KEY = "bls_oews"
OEWS_SOURCE_NAME = "US Bureau of Labor Statistics - Occupational Employment and Wage Statistics"
OEWS_SOURCE_URL = "https://www.bls.gov/oes/current/oes_nat.htm"

# Verified against BLS's own oe.txt and the OEWS technical notes during
# Phase 10 research - not paraphrased from memory.
OEWS_METHODOLOGY_NOTE = (
    "Semi-annual mail survey of non-farm establishments, published annually. "
    "Estimates cover wage and salary workers only - the self-employed and "
    "independent contractors are excluded entirely. For many occupations the "
    "annual figure is derived by multiplying the hourly wage by 2,080 hours "
    "rather than collected as an annual salary. Estimates that fail BLS "
    "reliability screens are not released, and appear here as missing rather "
    "than as zero."
)

# The single most misleading thing about reading OEWS as tech "comp".
# Quoted close to BLS's own wording rather than summarised loosely.
OEWS_WAGE_DEFINITION_NOTE = (
    "Straight-time gross pay. INCLUDES base rate, cost-of-living allowances, "
    "guaranteed pay, hazardous-duty pay, incentive pay such as commissions and "
    "production bonuses, and tips. EXCLUDES overtime, shift differentials, "
    "non-production bonuses (the typical annual bonus), employer-paid benefits, "
    "and equity or stock compensation."
)

# OEWS reference periods are always May of the labelled year; the release
# happens roughly a year later. Only vintages whose release date has been
# verified are listed - an unknown vintage stores NULL rather than a
# guessed date, since a fabricated publication date would undermine the
# freshness information this column exists to provide.
_VERIFIED_PUBLICATION_DATES: dict[int, date] = {
    2025: date(2026, 5, 15),
}


def _reference_period(year: int) -> date:
    """OEWS estimates describe May of the labelled year."""
    return date(year, 5, 1)


def fetch_and_persist(session: Session, provider: MarketDataProvider) -> list[MarketDataPoint]:
    """Stages (flushes) but does not commit - the caller owns the
    transaction, consistent with run_calculation and fetch_and_persist in
    fetch_exchange_rates.py.
    """
    country = session.scalar(select(Country).where(Country.code == "US"))
    if country is None:
        raise RuntimeError("US country row not found - run reference_data seed first.")
    currency = session.scalar(select(Currency).where(Currency.code == "USD"))
    if currency is None:
        raise RuntimeError("USD currency row not found - run reference_data seed first.")

    # Label comes along with the code: BLS v1 does not return an
    # occupation title in a plain data request, and the mapping rows
    # already carry the label verified against BLS's own oe.occupation
    # file. Falling back to the bare numeric code would show the user
    # "151252" instead of "Software Developers" - found by running the
    # real ingestion and reading the output rather than assuming the
    # provider's title lookup would populate.
    mapped = session.execute(
        select(
            JobFamilyOccupationMapping.external_code,
            JobFamilyOccupationMapping.external_label,
        )
        .where(
            JobFamilyOccupationMapping.country_id == country.id,
            JobFamilyOccupationMapping.taxonomy == provider.taxonomy,
        )
        .distinct()
    ).all()

    persisted: list[MarketDataPoint] = []
    for code, mapped_label in mapped:
        wages = provider.fetch_national_wages(code)
        if not wages.has_any_value:
            # A real outcome, not an error: the source publishes nothing
            # usable for this occupation. Logged so an operator can see
            # coverage gaps instead of silently ending up with fewer rows
            # than mappings.
            logger.warning(
                "No published market data for occupation", extra={"external_code": code}
            )
            continue

        reference_period = _reference_period(wages.reference_year)
        natural_key = {
            "country_id": country.id,
            "taxonomy": provider.taxonomy,
            "external_code": code,
            "geographic_scope": GeographicScope.NATIONAL,
            "area_code": "0000000",
            "reference_period": reference_period,
        }
        values = {
            "currency_id": currency.id,
            "external_label": wages.external_label or mapped_label,
            "area_name": "National",
            "percentile_10": wages.percentile_10,
            "percentile_25": wages.percentile_25,
            "percentile_50": wages.percentile_50,
            "percentile_75": wages.percentile_75,
            "percentile_90": wages.percentile_90,
            "mean_value": wages.mean_value,
            "employment_count": wages.employment_count,
            "reference_period_label": f"May {wages.reference_year}",
            "published_date": _VERIFIED_PUBLICATION_DATES.get(wages.reference_year),
            # Phase 11: a second source now exists, so rows carry a stable
            # machine identifier for grouping rather than the API having to
            # string-match display text.
            "source_key": OEWS_SOURCE_KEY,
            "source_name": OEWS_SOURCE_NAME,
            "source_url": OEWS_SOURCE_URL,
            "methodology_note": OEWS_METHODOLOGY_NOTE,
            "excludes_variable_compensation": True,
            "wage_definition_note": OEWS_WAGE_DEFINITION_NOTE,
        }

        persisted.append(_upsert(session, MarketDataPoint, natural_key, values))

    session.flush()
    return persisted


def main() -> None:
    from app.core.logging import configure_logging

    configure_logging()
    with BlsOewsProvider() as provider, SessionLocal() as session:
        points = fetch_and_persist(session, provider)
        session.commit()
        for point in points:
            print(
                f"{point.external_code} {point.external_label}: "
                f"p50={point.percentile_50} ({point.reference_period_label}) "
                f"[{point.source_name}]"
            )
        print(f"{len(points)} market data point(s) persisted.")


if __name__ == "__main__":
    main()
