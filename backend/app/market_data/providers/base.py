"""Market data provider abstraction (original architecture §10): one
interface, swappable concrete adapters - the same shape as Phase 6's
ExchangeRateProvider, and for the same reason: nothing outside this
package should know which statistical agency a figure came from.

The return type deliberately carries only what a source PUBLISHED, plus
the identifiers needed to attribute it. Source-level metadata that is a
property of the survey rather than of one datapoint (the wage definition,
methodology caveats, the release date of a given vintage) is attached by
the ingestion layer, which is where a real citation belongs - a provider
inventing a methodology string would be exactly the manufactured
provenance this phase exists to avoid.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class OccupationWages:
    """One occupation's published wage figures for one area and vintage.

    Every value is optional because real sources genuinely omit figures:
    OEWS suppresses estimates that fail its reliability screens
    (footnote 8, "Estimate not released"), and a mean-only source
    publishes no percentiles at all. A missing figure stays None all the
    way to the UI - never zero, never interpolated from its neighbours.
    """

    external_code: str
    # None when the source's response carried no occupation title (BLS v1
    # only returns catalog metadata on request). Deliberately NOT
    # defaulted to the bare code: a caller that already holds a verified
    # label should use it, and silently substituting "151252" for
    # "Software Developers" would strip exactly the source wording the UI
    # needs to show how broad the published bucket really is.
    external_label: str | None
    reference_year: int
    percentile_10: Decimal | None = None
    percentile_25: Decimal | None = None
    percentile_50: Decimal | None = None
    percentile_75: Decimal | None = None
    percentile_90: Decimal | None = None
    mean_value: Decimal | None = None
    employment_count: int | None = None

    @property
    def has_any_value(self) -> bool:
        """Whether the source published anything usable at all. An
        occupation whose every figure was suppressed is a real outcome,
        and callers need to tell it apart from a failed request.
        """
        return any(
            value is not None
            for value in (
                self.percentile_10,
                self.percentile_25,
                self.percentile_50,
                self.percentile_75,
                self.percentile_90,
                self.mean_value,
            )
        )


class MarketDataProviderError(Exception):
    """Raised when a provider can't return usable data - a bad HTTP
    status, a transport failure, or a response the API itself reports as
    unsuccessful. Distinct from "the source published no figure for this
    occupation", which is an ordinary result carried by OccupationWages
    with everything None, not an error.
    """


class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short, stable identifier for this provider, e.g. 'bls_oews'."""

    @property
    @abstractmethod
    def taxonomy(self) -> str:
        """The occupational classification this provider's codes belong
        to, e.g. 'SOC-2018'. Exposed on the interface so the ingestion
        layer can select the right JobFamilyOccupationMapping rows
        without hardcoding which provider implies which taxonomy.
        """

    @abstractmethod
    def fetch_national_wages(self, external_code: str) -> OccupationWages:
        """Latest published national wage figures for one occupation code.

        National-only by design for now: nothing in this app collects a
        user's location, so there is no honest basis for choosing a metro
        area on their behalf (see MarketDataPoint.geographic_scope).
        """
