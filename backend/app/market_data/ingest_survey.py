"""Persists aggregated Stack Overflow survey cells as MarketDataPoint
rows (Phase 11).

Run via:
    python -m app.market_data.ingest_survey /path/to/results.csv

The ~140MB annual release is NOT downloaded automatically: fetching it is
a deliberate operator step, so the path is passed in. Nothing here ever
runs on a request path.

Only occupations actually mapped to a job family are persisted, but
suppressed cells among them ARE persisted, carrying their sample size and
NULL figures. That is the point: a mapped role whose sample is too thin
must show up as "insufficient sample" rather than vanishing, so a gap in
the data is visible instead of invisible.
"""

import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.market_data.models import (
    GeographicScope,
    JobFamilyOccupationMapping,
    MarketDataPoint,
)
from app.market_data.providers.stackoverflow_survey import (
    MIN_PLAUSIBLE_ANNUAL_USD,
    SOURCE_KEY,
    SOURCE_NAME,
    SOURCE_URL,
    StackOverflowSurveyProvider,
)
from app.market_data.providers.survey_base import (
    MIN_SAMPLE_FOR_ANY_FIGURE,
    MIN_SAMPLE_FOR_TAIL_PERCENTILES,
    SurveyDataProvider,
)
from app.market_data.seed_survey import SURVEY_COUNTRIES
from app.reference_data.models import Country, Currency
from app.reference_data.upsert import upsert as _upsert

logger = logging.getLogger(__name__)

# The reference period is the survey year. Fielded and published in 2025;
# stored as a date for consistency with the OEWS rows, whose vintage is a
# month.
REFERENCE_PERIOD = date(2025, 1, 1)

METHODOLOGY_NOTE = (
    "Aggregated by this project from the Stack Overflow Annual Developer Survey 2025 "
    "public results (49,191 responses worldwide), licensed ODbL 1.0. Figures are "
    "self-reported by respondents, not employer-reported, and the respondent pool is "
    "people who read Stack Overflow - a narrower and more engaged population than the "
    "workforce as a whole. Amounts are Stack Overflow's own USD conversion, using the "
    "exchange rate on 25 June 2025. Responses are included only where the respondent "
    f"reported being employed and reported at least ${MIN_PLAUSIBLE_ANNUAL_USD:,.0f} per "
    "year (the raw file contains values as low as $1, which are not plausible annual "
    f"salaries). A cell is published only with at least {MIN_SAMPLE_FOR_ANY_FIGURE} "
    f"responses, and 10th/90th percentiles only with at least "
    f"{MIN_SAMPLE_FOR_TAIL_PERCENTILES}."
)

# Wage definition: the survey asks for total annual compensation, so
# unlike OEWS this is NOT base-pay-only. Stated explicitly because the
# two sources sit side by side and differ on exactly this point.
WAGE_DEFINITION_NOTE = (
    "Total annual compensation as reported by the respondent, which respondents may "
    "interpret to include bonus and equity - unlike the BLS figures shown alongside, "
    "which are straight-time base pay only. The two are therefore not measuring quite "
    "the same thing, which is part of why they are shown separately and never combined."
)

# Rendered as a PROMINENT banner, not a footnote - the same treatment the
# equity/bonus exclusion gets, because it changes how the numbers should
# be read.
_REPRESENTATIVENESS_NOTES: dict[str, str] = {
    "IN": (
        "Read these India figures with particular care. The respondents skew heavily "
        "toward product-company and globally-connected developers, and the resulting "
        "medians read high against broad Indian IT-services compensation. They are real "
        "reported figures, but they are NOT representative of the Indian developer "
        "market as a whole - treat them as one visible, self-selected slice of it "
        "rather than a general benchmark."
    ),
    "US": (
        "Respondents self-select from Stack Overflow's audience, which skews toward more "
        "engaged and more experienced developers than the workforce overall."
    ),
    "ES": (
        "Respondents self-select from Stack Overflow's audience, and the Spanish sample "
        "is small enough that role-level breakdowns are thin - the pooled figures carry "
        "far more weight than any single role."
    ),
}


def fetch_and_persist(session: Session, provider: SurveyDataProvider) -> list[MarketDataPoint]:
    """Stages (flushes) but does not commit - the caller owns the
    transaction, consistent with every other ingestion in this project.
    """
    currency = session.scalar(select(Currency).where(Currency.code == "USD"))
    if currency is None:
        raise RuntimeError("USD currency row not found - run reference_data seed first.")

    persisted: list[MarketDataPoint] = []
    for country_code in SURVEY_COUNTRIES:
        country = session.scalar(select(Country).where(Country.code == country_code))
        if country is None:
            continue

        mapped_codes = set(
            session.scalars(
                select(JobFamilyOccupationMapping.external_code).where(
                    JobFamilyOccupationMapping.country_id == country.id,
                    JobFamilyOccupationMapping.taxonomy == provider.taxonomy,
                )
            ).all()
        )
        if not mapped_codes:
            logger.warning(
                "No survey occupation mappings for country", extra={"country_code": country_code}
            )
            continue

        for cell in provider.fetch_cells(country_code):
            if cell.external_code not in mapped_codes:
                continue

            band = cell.experience_band
            natural_key = {
                "country_id": country.id,
                "taxonomy": provider.taxonomy,
                "external_code": cell.external_code,
                "geographic_scope": GeographicScope.NATIONAL,
                "area_code": "NATIONAL",
                "reference_period": REFERENCE_PERIOD,
                "experience_band_label": band.label if band else None,
            }
            values = {
                "currency_id": currency.id,
                "external_label": cell.external_label,
                "area_name": "National",
                "percentile_10": cell.percentile_10,
                "percentile_25": cell.percentile_25,
                "percentile_50": cell.percentile_50,
                "percentile_75": cell.percentile_75,
                "percentile_90": cell.percentile_90,
                "mean_value": cell.mean_value,
                # Population estimate vs sample count are different things
                # and never conflated: a survey aggregate has a sample
                # size and no employment estimate.
                "employment_count": None,
                "sample_size": cell.sample_size,
                "experience_min_years": band.min_years if band else None,
                "experience_max_years": band.max_years if band else None,
                "reference_period_label": provider.reference_period_label,
                "published_date": None,
                "source_key": SOURCE_KEY,
                "source_name": SOURCE_NAME,
                "source_url": SOURCE_URL,
                "methodology_note": METHODOLOGY_NOTE,
                "excludes_variable_compensation": False,
                "wage_definition_note": WAGE_DEFINITION_NOTE,
                "representativeness_note": _REPRESENTATIVENESS_NOTES.get(country_code),
            }
            persisted.append(_upsert(session, MarketDataPoint, natural_key, values))

    session.flush()
    return persisted


def main() -> None:
    import sys

    from app.core.logging import configure_logging

    configure_logging()
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python -m app.market_data.ingest_survey <path-to-results.csv>\n"
            "Download the release from https://survey.stackoverflow.co/ first - it is "
            "~140MB and is deliberately not fetched automatically."
        )
    path = Path(sys.argv[1])
    provider = StackOverflowSurveyProvider(path)
    with SessionLocal() as session:
        points = fetch_and_persist(session, provider)
        session.commit()
        published = [p for p in points if p.percentile_50 is not None]
        print(f"{len(points)} survey cell(s) persisted, {len(published)} with published figures.")
        for point in sorted(points, key=lambda p: (p.country_id, p.external_code))[:12]:
            band = point.experience_band_label or "all experience"
            figure = f"p50={point.percentile_50}" if point.percentile_50 else "SUPPRESSED"
            print(f"  {point.external_code[:38]:<40} {band:<15} n={point.sample_size:<5} {figure}")


if __name__ == "__main__":
    main()
