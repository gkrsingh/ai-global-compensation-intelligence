"""Response shapes for market context.

Two properties are load-bearing and deliberately not "cleaned up":

1. Every wage figure is Optional, and a figure the source did not publish
   stays null all the way to the client. It is never coerced to 0 and
   never interpolated from its neighbours - a wage of zero is a claim
   nobody made.
2. Provenance and caveats travel WITH the numbers in the same object,
   not in a separate metadata block a client could render independently
   (or forget to render). A consumer cannot get the distribution without
   also holding the source, the vintage, the match quality, and the
   wage-definition caveat.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.market_data.models import GeographicScope, MatchQuality


class WageDistributionOut(BaseModel):
    """The published distribution. Named a distribution, not an
    "estimate" or a "benchmark", because that is what the source
    publishes and what the UI must show - a single confident-looking
    number is precisely the misreading this phase is built to prevent.
    """

    percentile_10: Decimal | None
    percentile_25: Decimal | None
    percentile_50: Decimal | None
    percentile_75: Decimal | None
    percentile_90: Decimal | None
    mean_value: Decimal | None


class MarketOccupationOut(BaseModel):
    taxonomy: str
    external_code: str
    external_label: str

    # Carried alongside every figure rather than as a sibling lookup, so
    # a client physically cannot show the numbers without the caveat
    # about how well this occupation actually matches the role.
    match_quality: MatchQuality
    match_note: str

    geographic_scope: GeographicScope
    area_name: str
    currency_code: str

    distribution: WageDistributionOut
    employment_count: int | None

    reference_period_label: str
    published_date: date | None

    source_name: str
    source_url: str
    methodology_note: str

    # True for OEWS. Drives a prominent UI warning rather than a
    # footnote: for tech roles, non-production bonuses and equity are
    # routinely 20-50% of the package, so comparing a total-comp offer
    # against this figure without saying so would actively mislead.
    excludes_variable_compensation: bool
    wage_definition_note: str


class MarketContextOut(BaseModel):
    """Market context for one job family in one country.

    `available` is an explicit field rather than being implied by an
    empty list, and `unavailable_reason` is populated whenever it is
    False. "We have no data for this" is a real, honest answer this
    project states out loud (India is genuinely unsupported - see
    README), not something a client should have to infer from silence.
    """

    country_code: str
    job_family_id: int
    job_family_name: str
    available: bool
    unavailable_reason: str | None
    occupations: list[MarketOccupationOut]
