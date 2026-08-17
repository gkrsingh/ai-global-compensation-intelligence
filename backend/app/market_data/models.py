"""External market compensation data (original architecture §10,
deferred since Phase 2).

The central distinction this whole module exists to preserve: everything
else persisted by this project is a FACT (a government published a tax
bracket; a central bank published an exchange rate - verifiably right or
wrong). A market compensation figure is a STATISTICAL ESTIMATE from a
survey, with a sample, a methodology, real uncertainty, and a shelf life.
Blurring those two would recreate - one layer up - exactly the
hallucinated-market-data problem this project exists to solve, so the
separation is enforced structurally here, not just by convention:

- MarketDataPoint has NO foreign key to Calculation, CompensationInput,
  or anything else in the deterministic pipeline. Nothing in the
  calculation engine can read it, by construction.
- It carries provenance as required columns (source, reference period,
  methodology note), so a bare number with no citation cannot be stored.
- It records what the source ACTUALLY publishes, including what the
  figure excludes - see excludes_variable_compensation below.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.reference_data.models import Country, Currency, JobFamily


class MatchQuality(enum.StrEnum):
    """How honestly an internal JobFamily maps onto an external
    occupation code. Stored per-mapping and surfaced all the way to the
    UI rather than hidden, because the quality genuinely varies and a
    confident-looking number against the wrong occupation is worse than
    no number at all.

    Determined during Phase 10 research against the real SOC-2018 list -
    not guessed. CLOSE means the external occupation substantially IS the
    internal family. BROAD means the external bucket is materially wider
    than the family (or the family spans several dissimilar codes). POOR
    means no good match exists and the nearest code means something
    genuinely different - kept, labeled, and shown as such rather than
    silently dropped or silently presented as if it were fine.
    """

    CLOSE = "close"
    BROAD = "broad"
    POOR = "poor"


class GeographicScope(enum.StrEnum):
    """OEWS publishes national, state, and metropolitan estimates. Only
    NATIONAL is ingested today because nothing in this app collects a
    user's location (CompensationInput has country_id and no sub-national
    field), so there is no honest way to pick a metro on the user's
    behalf. STATE/METRO exist here now so adding them later is an
    ingestion + UI change, not a migration.
    """

    NATIONAL = "national"
    STATE = "state"
    METRO = "metro"


class JobFamilyOccupationMapping(Base):
    """The explicit, stored bridge between this project's small internal
    JobFamily taxonomy and a national occupational classification.

    Deliberately a table, never a hardcoded `if family == "Software
    Engineering"` branch - the same no-country-branching rule held since
    Phase 2's tax engine. A JobFamily maps to MANY codes (Sales spans
    several SOC codes with wildly different pay), so this is many-to-many
    by construction.

    Country-scoped because occupational taxonomies are national: the US
    uses SOC, Spain CNO, India NCO. Phase 10 research considered ISCO-08
    as a cross-country pivot and rejected it: routing SOC -> ISCO ->
    internal adds a lossy translation layer for zero benefit while
    exactly one rich source (US OEWS, SOC-native) is wired up. `taxonomy`
    is a column rather than an assumption so a second national taxonomy
    slots in without a schema change.
    """

    __tablename__ = "job_family_occupation_mappings"
    __table_args__ = (
        UniqueConstraint(
            "job_family_id",
            "country_id",
            "taxonomy",
            "external_code",
            name="uq_job_family_occupation_mappings_family_country_taxonomy_code",
        ),
        Index(
            "ix_job_family_occupation_mappings_lookup",
            "country_id",
            "taxonomy",
            "external_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_family_id: Mapped[int] = mapped_column(ForeignKey("job_families.id"))
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"))
    taxonomy: Mapped[str] = mapped_column(
        String(32), comment="Occupational classification standard, e.g. 'SOC-2018'."
    )
    external_code: Mapped[str] = mapped_column(
        String(128),
        comment="Code within `taxonomy`, e.g. '151252' for SOC 15-1252, or a survey's own "
        "role label. Widened from 16 in Phase 11: a statistical classification uses short "
        "numeric codes, but a survey's identifier for a role IS its descriptive string "
        "(e.g. 'Developer, embedded applications or devices'). Storing the source's own "
        "value keeps the row traceable rather than inventing local slugs.",
    )
    external_label: Mapped[str] = mapped_column(
        String(256),
        comment="The source's own name for this occupation, stored verbatim so the UI can show "
        "exactly how broad the bucket is rather than paraphrasing it.",
    )
    match_quality: Mapped[MatchQuality] = mapped_column(
        Enum(MatchQuality, name="match_quality"),
    )
    match_note: Mapped[str] = mapped_column(
        Text,
        comment="Plain-language statement of what this mapping does and does not capture. "
        "Required, not nullable: every mapping is lossy in some way and saying how is the point.",
    )

    job_family: Mapped[JobFamily] = relationship()
    country: Mapped[Country] = relationship()


class MarketDataPoint(Base):
    """One published wage estimate for one occupation, area, and
    reference period.

    Keyed by EXTERNAL occupation code, not by JobFamily: this row records
    what the statistical agency actually published about SOC 15-1252, and
    that fact is independent of how this project's own taxonomy happens
    to map onto it. JobFamilyOccupationMapping does the joining, so a
    remapping never rewrites ingested source data.

    Note what is deliberately ABSENT: there is no experience_level_id.
    OEWS publishes wage PERCENTILES, and a percentile is not a seniority
    level - treating "75th percentile" as "senior" would be a fabricated
    inference, not a fact from the source. The distribution is stored and
    shown as a distribution, and the user locates themselves in it.
    """

    __tablename__ = "market_data_points"
    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "taxonomy",
            "external_code",
            "geographic_scope",
            "area_code",
            "reference_period",
            # Added in Phase 11: the same occupation and vintage now
            # legitimately yields several rows, one per experience band
            # (plus one with NULL for the band-independent figure), so the
            # band is part of what makes a row unique. NULL participates
            # in a UNIQUE constraint as "distinct" in Postgres, which is
            # exactly right here - the band-independent row must be able
            # to coexist with the banded ones.
            "experience_band_label",
            name="uq_market_data_points_natural_key",
        ),
        # At least one actual figure, or the row is provenance with no
        # data. Written as an explicit OR over every value column rather
        # than requiring the median specifically, because a mean-only
        # source is a real shape this project already knows it will meet
        # (Spain's INE publishes a mean per occupation and percentiles
        # only per region - never both together, confirmed against the
        # live INE API during Phase 10 research). Spain is not ingested
        # this phase, but the schema staying able to represent mean-only
        # data is what keeps adding it later a data change, not a
        # migration.
        # Relaxed in Phase 11, deliberately and narrowly. The original
        # rule ("a row must carry at least one figure, or it is a citation
        # attached to nothing") was right for a source that publishes
        # finished estimates. Phase 11 introduced a genuinely new and
        # intentional row type: a SUPPRESSED survey cell, where every
        # figure is NULL precisely because the sample was too small to
        # publish, and the row exists so that absence is visible with its
        # sample size attached rather than silently missing.
        #
        # So the requirement becomes: a row with no figures must at least
        # explain itself with a sample count. A published-estimate source
        # still cannot store an empty row, because it has no sample_size.
        # The constraint surfaced this conflict by failing the real
        # ingestion, which is exactly what it was for - it forced the new
        # case to be made explicit instead of quietly dropped.
        CheckConstraint(
            "percentile_10 IS NOT NULL OR percentile_25 IS NOT NULL OR "
            "percentile_50 IS NOT NULL OR percentile_75 IS NOT NULL OR "
            "percentile_90 IS NOT NULL OR mean_value IS NOT NULL OR "
            "sample_size IS NOT NULL",
            name="ck_market_data_points_has_at_least_one_value",
        ),
        Index("ix_market_data_points_lookup", "country_id", "taxonomy", "external_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"))
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    taxonomy: Mapped[str] = mapped_column(String(32))
    # Same widening as JobFamilyOccupationMapping.external_code above -
    # the two must stay in step, since they are joined on this value.
    external_code: Mapped[str] = mapped_column(String(128))
    external_label: Mapped[str] = mapped_column(String(256))

    geographic_scope: Mapped[GeographicScope] = mapped_column(
        Enum(GeographicScope, name="geographic_scope")
    )
    area_code: Mapped[str] = mapped_column(
        String(16), comment="Source's own area code, e.g. OEWS '0000000' for National."
    )
    area_name: Mapped[str] = mapped_column(String(128))

    # Every value column is nullable: a source may publish some
    # percentiles and not others, or a mean and no distribution at all.
    # NULL means "this source did not publish this figure" and must never
    # be rendered as zero or silently interpolated.
    percentile_10: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    percentile_25: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    percentile_50: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    percentile_75: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    percentile_90: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    mean_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    employment_count: Mapped[int | None] = mapped_column(
        Integer, comment="Estimated number of workers in this occupation/area - a rough proxy for "
        "how much weight the estimate can bear."
    )

    # Phase 11. How many individual responses this cell was computed from.
    # NULL for a source that publishes finished estimates rather than
    # microdata (BLS OEWS reports employment, which is a population
    # estimate, not a sample count) - the two must never be conflated,
    # which is why they are separate columns.
    #
    # For survey-derived rows this is the single most important number on
    # the row after the figures themselves: it is what tells a reader
    # whether the distribution means anything, and it is shown in the UI
    # rather than kept internal.
    sample_size: Mapped[int | None] = mapped_column(Integer)

    # Phase 11's seniority dimension, stored EXACTLY as measured: bands of
    # reported years of professional experience. Deliberately NOT a
    # foreign key to ExperienceLevel (Junior/Mid/Senior/...) - relabelling
    # "6-10 yrs" as "Senior" would be precisely the inference no source
    # publishes, the same trap Phase 10 avoided by refusing to read a
    # percentile as a level. Years in, years out.
    #
    # NULL means the row is not broken down by experience at all, which is
    # the honest state for every BLS row (OEWS publishes no seniority
    # breakdown whatsoever).
    experience_band_label: Mapped[str | None] = mapped_column(
        String(32), comment="e.g. '6-10 yrs'. NULL = not broken down by experience."
    )
    experience_min_years: Mapped[int | None] = mapped_column(Integer)
    experience_max_years: Mapped[int | None] = mapped_column(
        Integer, comment="NULL with a non-NULL min means an open-ended top band (e.g. '11+ yrs')."
    )

    reference_period: Mapped[date] = mapped_column(
        Date,
        comment="First day of the period the estimate DESCRIBES (e.g. 2025-05-01 for OEWS "
        "'May 2025'), which is not when it was published - see published_date.",
    )
    reference_period_label: Mapped[str] = mapped_column(
        String(64), comment="The source's own name for the period, e.g. 'May 2025'."
    )
    published_date: Mapped[date | None] = mapped_column(
        Date,
        comment="When the source released this estimate. Stored separately from reference_period "
        "because the lag is large and material: OEWS May 2025 data was released 2026-05-15.",
    )

    # Provenance is required, not optional: a market figure with no
    # citation is exactly what this project refuses to produce.
    #
    # source_key (Phase 11) is the stable machine identifier - added once
    # a second source existed, so the API and UI can group and label by
    # source without string-matching source_name, which is display text
    # and free to change.
    source_key: Mapped[str] = mapped_column(
        String(32), comment="Stable source id, e.g. 'bls_oews', 'stackoverflow_survey'."
    )
    source_name: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512))
    methodology_note: Mapped[str] = mapped_column(
        Text, comment="Sample/collection method and known limitations, in the source's own terms."
    )

    # Phase 11. When non-NULL, the UI renders this as a PROMINENT banner,
    # not a footnote - the same treatment
    # excludes_variable_compensation already gets, and for the same
    # reason: a caveat that changes how a number should be read is
    # useless if the reader finds it after the number.
    #
    # The concrete case this exists for: the Stack Overflow survey's
    # India sample skews toward product-company and globally-connected
    # developers and reads high against broad Indian IT-services
    # compensation. Left invisible, this tool would replace one
    # non-representative skew with a different one - the exact problem it
    # was built to avoid.
    representativeness_note: Mapped[str | None] = mapped_column(Text)

    # The single most misleading thing about using OEWS for tech
    # compensation, promoted to a real boolean rather than buried in
    # methodology_note prose so the UI can render it as a prominent
    # warning generically (and so a future source that DOES include total
    # compensation simply sets this False).
    #
    # OEWS wages are straight-time gross pay: base rate, cost-of-living
    # allowances, commissions and PRODUCTION bonuses are included;
    # overtime, shift differentials, NONPRODUCTION bonuses (the typical
    # annual tech bonus) and employer-provided benefits are excluded, as
    # is equity. For tech roles where bonus and stock are routinely
    # 20-50% of the package, quietly comparing a total-comp offer against
    # this figure would actively mislead someone mid-negotiation.
    excludes_variable_compensation: Mapped[bool] = mapped_column(Boolean)
    wage_definition_note: Mapped[str] = mapped_column(
        Text, comment="Precisely what this figure counts as pay, in the source's own terms."
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped[Country] = relationship()
    currency: Mapped[Currency] = relationship()
