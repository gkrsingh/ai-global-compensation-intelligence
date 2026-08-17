"""Market context endpoint.

Deliberately NOT rate-limited, unlike Phase 9's treatment of /auth/* and
/ai-insights: this endpoint only ever reads already-persisted rows. It
makes no external call and incurs no per-request cost, so it carries the
same (absent) limiting as every other read endpoint in this API. The
external BLS call happens exclusively in the offline ingestion script
(app/market_data/ingest.py), which is where any throttling concern
actually lives.

Also deliberately unauthenticated, matching reference_data/api.py: these
are public government statistics, not user-owned data.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError
from app.db.session import get_db
from app.market_data.models import (
    GeographicScope,
    JobFamilyOccupationMapping,
    MarketDataPoint,
)
from app.market_data.schemas import (
    MarketContextOut,
    MarketOccupationOut,
    WageDistributionOut,
)
from app.reference_data.models import Country, JobFamily

logger = logging.getLogger(__name__)

router = APIRouter()

# Stated once, surfaced verbatim to the client. Phrased as a plain fact
# about coverage rather than an apology or an error, because that is what
# it is - see the Phase 10 research findings and the README's market data
# section for exactly why India and Spain are not covered.
_NO_COVERAGE_FOR_COUNTRY = (
    "No market compensation data is available for this country. This project only "
    "ingests official government statistical sources, and no free, occupation-level "
    "wage distribution is published for this country in a form that can be cited "
    "honestly."
)
_NO_MAPPING_FOR_FAMILY = (
    "No occupation mapping exists for this job family in this country, so there is "
    "no published occupation whose wage distribution could be shown."
)
_NO_DATA_FOR_MAPPED_OCCUPATIONS = (
    "This job family is mapped to published occupations, but no wage data has been "
    "ingested for them yet."
)


@router.get("/market-context", response_model=MarketContextOut)
def get_market_context(
    job_family_id: int,
    country_code: str,
    db: Session = Depends(get_db),
) -> MarketContextOut:
    """Published market wage distributions for a job family in a country.

    Returns 200 with available=False and a stated reason when there is
    genuinely no data, rather than 404 or an empty list: "this country
    has no citable source" is a real answer, not a failed lookup. A 404
    is reserved for an actually-unknown country or job family, which is a
    caller error rather than a coverage gap.
    """
    country = db.scalar(select(Country).where(Country.code == country_code.upper()))
    if country is None:
        raise AppError(
            f"Unknown country code: {country_code}", code="unknown_country", status_code=404
        )

    job_family = db.get(JobFamily, job_family_id)
    if job_family is None:
        raise AppError(
            f"Unknown job family id: {job_family_id}", code="unknown_job_family", status_code=404
        )

    def _empty(reason: str) -> MarketContextOut:
        return MarketContextOut(
            country_code=country.code,
            job_family_id=job_family.id,
            job_family_name=job_family.name,
            available=False,
            unavailable_reason=reason,
            occupations=[],
        )

    mappings = list(
        db.scalars(
            select(JobFamilyOccupationMapping).where(
                JobFamilyOccupationMapping.job_family_id == job_family.id,
                JobFamilyOccupationMapping.country_id == country.id,
            )
        ).all()
    )
    if not mappings:
        # Distinguishes "we don't cover this country at all" from "we
        # cover it but not this family" - two genuinely different
        # situations that would otherwise collapse into one vague message.
        any_for_country = db.scalar(
            select(JobFamilyOccupationMapping.id)
            .where(JobFamilyOccupationMapping.country_id == country.id)
            .limit(1)
        )
        return _empty(
            _NO_MAPPING_FOR_FAMILY if any_for_country else _NO_COVERAGE_FOR_COUNTRY
        )

    occupations: list[MarketOccupationOut] = []
    for mapping in mappings:
        point = db.scalar(
            select(MarketDataPoint)
            .where(
                MarketDataPoint.country_id == country.id,
                MarketDataPoint.taxonomy == mapping.taxonomy,
                MarketDataPoint.external_code == mapping.external_code,
                MarketDataPoint.geographic_scope == GeographicScope.NATIONAL,
            )
            .options(selectinload(MarketDataPoint.currency))
            # Newest vintage wins. Older rows are deliberately retained by
            # the ingestion upsert as history rather than overwritten.
            .order_by(MarketDataPoint.reference_period.desc())
            .limit(1)
        )
        if point is None:
            continue

        occupations.append(
            MarketOccupationOut(
                taxonomy=mapping.taxonomy,
                external_code=mapping.external_code,
                # The source's own wording for the occupation, not the
                # internal family name - the whole point is letting the
                # user see how broad the published bucket really is.
                external_label=point.external_label,
                match_quality=mapping.match_quality,
                match_note=mapping.match_note,
                geographic_scope=point.geographic_scope,
                area_name=point.area_name,
                currency_code=point.currency.code,
                distribution=WageDistributionOut(
                    percentile_10=point.percentile_10,
                    percentile_25=point.percentile_25,
                    percentile_50=point.percentile_50,
                    percentile_75=point.percentile_75,
                    percentile_90=point.percentile_90,
                    mean_value=point.mean_value,
                ),
                employment_count=point.employment_count,
                reference_period_label=point.reference_period_label,
                published_date=point.published_date,
                source_name=point.source_name,
                source_url=point.source_url,
                methodology_note=point.methodology_note,
                excludes_variable_compensation=point.excludes_variable_compensation,
                wage_definition_note=point.wage_definition_note,
            )
        )

    if not occupations:
        logger.warning(
            "Job family is mapped but has no ingested market data",
            extra={"job_family_id": job_family.id, "country_code": country.code},
        )
        return _empty(_NO_DATA_FOR_MAPPED_OCCUPATIONS)

    # Best match first so the UI leads with the most defensible figure,
    # then by median descending purely for stable, predictable ordering.
    _QUALITY_ORDER = {"close": 0, "broad": 1, "poor": 2}
    occupations.sort(
        key=lambda o: (
            _QUALITY_ORDER.get(str(o.match_quality), 99),
            -(o.distribution.percentile_50 or 0),
        )
    )

    return MarketContextOut(
        country_code=country.code,
        job_family_id=job_family.id,
        job_family_name=job_family.name,
        available=True,
        unavailable_reason=None,
        occupations=occupations,
    )
