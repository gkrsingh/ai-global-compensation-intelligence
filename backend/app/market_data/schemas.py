"""Response shapes for market context.

Restructured in Phase 11 around SOURCES, because a second source now
exists and the two genuinely disagree - BLS reports US software
developers at a $135,980 median (employer-reported, base pay only) while
the survey reports full-stack developers at $140,000 (self-reported,
total compensation). Those are different measurements of different
populations, so the response nests occupations UNDER their source and
never merges them. Averaging two differently-methodologied figures would
itself be a fabricated number - the exact thing this project refuses to
produce.

Three properties are load-bearing and deliberately not "cleaned up":

1. Every figure is Optional, and a figure the source did not publish (or
   that was suppressed for a thin sample) stays null all the way to the
   client. Never coerced to 0, never interpolated.
2. Provenance and caveats live on the source object that WRAPS the
   occupations, so a client cannot reach a number without passing through
   its citation, methodology, and warnings.
3. A suppressed cell is still returned, carrying its sample_size, so the
   UI can show "insufficient sample" rather than silently omitting it. An
   invisible gap looks like no gap at all.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.market_data.models import GeographicScope, MatchQuality


class WageDistributionOut(BaseModel):
    """The published distribution. Named a distribution, not an
    "estimate" or a "benchmark", because that is what the source
    publishes and what the UI must show - a single confident-looking
    number is precisely the misreading this feature is built to prevent.
    """

    percentile_10: Decimal | None
    percentile_25: Decimal | None
    percentile_50: Decimal | None
    percentile_75: Decimal | None
    percentile_90: Decimal | None
    mean_value: Decimal | None


class MarketEntryOut(BaseModel):
    """One row of figures for an occupation: either the figure across all
    experience levels (experience_band_label is null) or one
    years-of-experience band.

    Bands are reported as MEASURED - "6-10 yrs", never relabelled
    "Senior". No source publishes that mapping, so asserting it would be
    an inference, the same line Phase 10 held when it refused to read a
    wage percentile as a seniority level.
    """

    experience_band_label: str | None
    experience_min_years: int | None
    experience_max_years: int | None

    # Number of individual survey responses behind this cell. Null for a
    # source that publishes finished estimates rather than microdata.
    # Shown in the UI, not kept internal: it is what tells a reader
    # whether the distribution means anything.
    sample_size: int | None
    # Population employment estimate. A different thing from sample_size
    # and never conflated with it.
    employment_count: int | None

    distribution: WageDistributionOut
    # True when the sample was too small to publish any figure. The entry
    # is still returned so the shortfall is visible with its count.
    suppressed: bool


class MarketOccupationOut(BaseModel):
    taxonomy: str
    external_code: str
    external_label: str

    # Carried on the occupation rather than as a sibling lookup, so a
    # client cannot show the numbers without the caveat about how well
    # this occupation actually matches the role.
    match_quality: MatchQuality
    match_note: str

    geographic_scope: GeographicScope
    area_name: str
    currency_code: str

    entries: list[MarketEntryOut]


class MarketSourceOut(BaseModel):
    """One source's view of a job family, with its own provenance.

    Source-level metadata sits here rather than being repeated on every
    occupation, but it still wraps them - so it cannot be skipped.
    """

    source_key: str
    source_name: str
    source_url: str
    reference_period_label: str
    published_date: date | None
    methodology_note: str

    excludes_variable_compensation: bool
    wage_definition_note: str

    # When present, the UI renders this as a PROMINENT banner, not a
    # footnote. Exists chiefly for the survey's India sample, which skews
    # toward product-company and globally-connected developers and reads
    # high against broad Indian IT-services compensation.
    representativeness_note: str | None

    occupations: list[MarketOccupationOut]


class MarketContextOut(BaseModel):
    """Market context for one job family in one country.

    `available` is an explicit field rather than being implied by an empty
    list, and `unavailable_reason` is populated whenever it is False.
    "We have no data for this" is a real answer this project states out
    loud, not something a client should have to infer from silence.
    """

    country_code: str
    job_family_id: int
    job_family_name: str
    available: bool
    unavailable_reason: str | None
    sources: list[MarketSourceOut]
