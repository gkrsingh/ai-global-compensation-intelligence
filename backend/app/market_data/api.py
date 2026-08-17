"""Market context endpoint.

Deliberately NOT rate-limited, unlike Phase 9's treatment of /auth/* and
/ai-insights: this endpoint only ever reads already-persisted rows. It
makes no external call and incurs no per-request cost, so it carries the
same (absent) limiting as every other read endpoint in this API. The BLS
call and the survey aggregation both happen exclusively in offline
ingestion scripts.

Also deliberately unauthenticated, matching reference_data/api.py: these
are public statistics, not user-owned data.
"""

import logging
from collections import defaultdict

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
    MarketEntryOut,
    MarketOccupationOut,
    MarketSourceOut,
    WageDistributionOut,
)
from app.reference_data.models import Country, JobFamily

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_COVERAGE_FOR_COUNTRY = (
    "No market compensation data is available for this country. This project only "
    "ingests sources whose methodology and sample can be cited honestly, and no such "
    "occupation-level wage data is currently available for this country."
)
_NO_MAPPING_FOR_FAMILY = (
    "No occupation mapping exists for this job family in this country, so there is "
    "no published occupation whose wage distribution could be shown."
)
_NO_DATA_FOR_MAPPED_OCCUPATIONS = (
    "This job family is mapped to published occupations, but no wage data has been "
    "ingested for them yet."
)

# Presentation order only. Official, employer-reported statistics are
# shown before self-reported survey aggregates so the reader meets the
# more methodologically conservative source first - explicitly NOT a
# claim that either is more correct. Neither is preferred, combined, or
# averaged anywhere.
_SOURCE_ORDER = {"bls_oews": 0}
_QUALITY_ORDER = {"close": 0, "broad": 1, "poor": 2}


@router.get("/market-context", response_model=MarketContextOut)
def get_market_context(
    job_family_id: int,
    country_code: str,
    db: Session = Depends(get_db),
) -> MarketContextOut:
    """Published market wage distributions for a job family in a country,
    grouped by source.

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
            sources=[],
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
        # cover it but not this family" - genuinely different situations
        # that would otherwise collapse into one vague message.
        any_for_country = db.scalar(
            select(JobFamilyOccupationMapping.id)
            .where(JobFamilyOccupationMapping.country_id == country.id)
            .limit(1)
        )
        return _empty(_NO_MAPPING_FOR_FAMILY if any_for_country else _NO_COVERAGE_FOR_COUNTRY)

    mapping_by_key = {(m.taxonomy, m.external_code): m for m in mappings}
    points = list(
        db.scalars(
            select(MarketDataPoint)
            .where(
                MarketDataPoint.country_id == country.id,
                MarketDataPoint.geographic_scope == GeographicScope.NATIONAL,
                MarketDataPoint.taxonomy.in_({m.taxonomy for m in mappings}),
                MarketDataPoint.external_code.in_({m.external_code for m in mappings}),
            )
            .options(selectinload(MarketDataPoint.currency))
            .order_by(MarketDataPoint.reference_period.desc())
        ).all()
    )

    # source -> occupation -> newest vintage's rows. Older vintages are
    # retained by ingestion as history and must not be mixed in with the
    # current ones, so only the newest reference_period per occupation is
    # kept.
    grouped: defaultdict[str, defaultdict[tuple[str, str], list[MarketDataPoint]]] = defaultdict(
        lambda: defaultdict(list)
    )
    newest_period: dict[tuple[str, str, str], object] = {}
    for point in points:
        key = (point.source_key, point.taxonomy, point.external_code)
        if key not in newest_period:
            newest_period[key] = point.reference_period
        if point.reference_period != newest_period[key]:
            continue
        grouped[point.source_key][(point.taxonomy, point.external_code)].append(point)

    sources: list[MarketSourceOut] = []
    for source_key, by_occupation in grouped.items():
        occupations: list[MarketOccupationOut] = []
        exemplar: MarketDataPoint | None = None

        for (taxonomy, code), rows in by_occupation.items():
            mapping = mapping_by_key.get((taxonomy, code))
            if mapping is None:
                continue
            exemplar = exemplar or rows[0]

            entries = [
                MarketEntryOut(
                    experience_band_label=row.experience_band_label,
                    experience_min_years=row.experience_min_years,
                    experience_max_years=row.experience_max_years,
                    sample_size=row.sample_size,
                    employment_count=row.employment_count,
                    distribution=WageDistributionOut(
                        percentile_10=row.percentile_10,
                        percentile_25=row.percentile_25,
                        percentile_50=row.percentile_50,
                        percentile_75=row.percentile_75,
                        percentile_90=row.percentile_90,
                        mean_value=row.mean_value,
                    ),
                    # A cell with no median was withheld for a thin
                    # sample; it is returned anyway so the gap is visible.
                    suppressed=row.percentile_50 is None,
                )
                for row in rows
            ]
            # All-experience first, then bands from least to most
            # experienced, so the breakdown reads in a natural order.
            entries.sort(
                key=lambda e: (
                    0 if e.experience_min_years is None else 1,
                    e.experience_min_years or 0,
                )
            )

            occupations.append(
                MarketOccupationOut(
                    taxonomy=taxonomy,
                    external_code=code,
                    # The source's own wording, not the internal family
                    # name - the point is showing how broad the published
                    # bucket really is.
                    external_label=rows[0].external_label,
                    match_quality=mapping.match_quality,
                    match_note=mapping.match_note,
                    geographic_scope=rows[0].geographic_scope,
                    area_name=rows[0].area_name,
                    currency_code=rows[0].currency.code,
                    entries=entries,
                )
            )

        if exemplar is None or not occupations:
            continue

        # Best match first so the most defensible figure leads. Within a
        # quality tier, occupations with any publishable figure come
        # before fully-suppressed ones.
        occupations.sort(
            key=lambda o: (
                _QUALITY_ORDER.get(str(o.match_quality), 99),
                all(e.suppressed for e in o.entries),
                o.external_label,
            )
        )

        sources.append(
            MarketSourceOut(
                source_key=source_key,
                source_name=exemplar.source_name,
                source_url=exemplar.source_url,
                reference_period_label=exemplar.reference_period_label,
                published_date=exemplar.published_date,
                methodology_note=exemplar.methodology_note,
                excludes_variable_compensation=exemplar.excludes_variable_compensation,
                wage_definition_note=exemplar.wage_definition_note,
                representativeness_note=exemplar.representativeness_note,
                occupations=occupations,
            )
        )

    if not sources:
        logger.warning(
            "Job family is mapped but has no ingested market data",
            extra={"job_family_id": job_family.id, "country_code": country.code},
        )
        return _empty(_NO_DATA_FOR_MAPPED_OCCUPATIONS)

    sources.sort(key=lambda s: (_SOURCE_ORDER.get(s.source_key, 99), s.source_name))

    return MarketContextOut(
        country_code=country.code,
        job_family_id=job_family.id,
        job_family_name=job_family.name,
        available=True,
        unavailable_reason=None,
        sources=sources,
    )
