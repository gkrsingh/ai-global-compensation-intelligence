"""Abstraction for market data derived from SURVEY MICRODATA, as opposed
to MarketDataProvider (providers/base.py) which fetches figures an agency
has already computed and published.

Deliberately a second, sibling interface rather than a generalisation of
the first: the two genuinely differ in shape. BLS answers "what did you
publish for occupation X?" one occupation at a time; a microdata source
answers "here is every cell I can compute for this country", and only it
has to reason about sample sizes and suppression at all. Forcing both
through one method would make each awkward and would push
suppression logic somewhere it does not belong.

The suppression rules live here, on the interface, because they are the
part that must not vary by implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

# Two tiers, because the tails of a distribution need more data than its
# centre. At n=30 a 10th percentile rests on roughly three observations -
# noise wearing a statistic. A median at the same n is far steadier.
#
# Follows BLS's own precedent of withholding estimates that fail its
# reliability screens, rather than publishing everything and hoping the
# reader discounts appropriately.
MIN_SAMPLE_FOR_ANY_FIGURE = 30
MIN_SAMPLE_FOR_TAIL_PERCENTILES = 100


@dataclass(frozen=True)
class ExperienceBand:
    """A band of reported years of professional experience.

    Stored and displayed as YEARS, never relabelled to a seniority title.
    "6-10 yrs" is a fact about what respondents reported; calling it
    "Senior" would be an inference no source publishes - the same line
    Phase 10 held when it refused to read a wage percentile as a level.
    """

    label: str
    min_years: int
    # None = open-ended top band ("11+ yrs").
    max_years: int | None


@dataclass(frozen=True)
class SurveyCell:
    """One aggregated cell: a country/occupation/experience combination
    with the percentiles computed from the real responses in it.

    Percentiles are None when the cell's sample is too small to support
    them (see the two tiers above). A None here means "not published
    because the sample cannot bear it" - which the UI must SHOW as
    insufficient sample rather than silently omit, so a thin cell is
    visibly thin instead of invisibly absent.
    """

    external_code: str
    external_label: str
    experience_band: ExperienceBand | None
    sample_size: int
    percentile_10: Decimal | None
    percentile_25: Decimal | None
    percentile_50: Decimal | None
    percentile_75: Decimal | None
    percentile_90: Decimal | None
    mean_value: Decimal | None

    @property
    def is_suppressed(self) -> bool:
        """True when the sample was too small to publish any figure. The
        cell still exists and still carries its sample_size, precisely so
        the absence can be shown with its reason attached.
        """
        return self.percentile_50 is None


class SurveyDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short, stable identifier, e.g. 'stackoverflow_survey'."""

    @property
    @abstractmethod
    def taxonomy(self) -> str:
        """Occupation classification these codes belong to. A survey's own
        role taxonomy is not SOC/CNO/NCO, so it gets its own identifier
        and flows through the same JobFamilyOccupationMapping bridge.
        """

    @property
    @abstractmethod
    def reference_period_label(self) -> str:
        """The source's own name for the vintage, e.g. '2025 survey'."""

    @abstractmethod
    def fetch_cells(self, country_code: str) -> list[SurveyCell]:
        """Every cell computable for one country, including suppressed
        ones. Returns an empty list for a country the source does not
        cover - distinct from covering it and finding nothing publishable.
        """
