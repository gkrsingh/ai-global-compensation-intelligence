"""Exchange rate provider abstraction (original architecture §10): one
interface, swappable concrete adapters. Nothing outside this module ever
talks to a specific rate source directly - not the ingestion script
(fetch_exchange_rates.py), and definitely not Phase 3's pure
convert_amount(), which only ever reads already-persisted ExchangeRate
rows and has no idea a provider exists at all.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import httpx


@dataclass(frozen=True)
class Rate:
    base: str
    quote: str
    rate: Decimal
    as_of_date: date
    source: str


class ExchangeRateProviderError(Exception):
    """Raised when a provider can't return a usable rate - a bad HTTP
    status, a malformed response, or a response that simply doesn't
    contain the requested currency.
    """


class ExchangeRateProvider(ABC):
    @abstractmethod
    def get_rate(self, base: str, quote: str, as_of: date) -> Rate:
        """The base->quote rate nearest to (at or before) as_of.

        The returned Rate.as_of_date reflects the date the rate actually
        applies to, per the provider - which can differ from the
        requested date (a weekend or holiday falls back to the nearest
        prior business day, confirmed empirically against the real
        Frankfurter API before writing this interface). Callers must
        never assume the requested and returned dates match; that's the
        whole reason this field exists on the return value rather than
        being implied by the call.
        """


class FrankfurterProvider(ExchangeRateProvider):
    """Adapter for api.frankfurter.dev.

    Pinned to providers=ECB explicitly rather than Frankfurter's default
    blended-across-84-central-banks rate: blended rates can shift decimal
    places as more providers report in, which makes them a poor fit for
    a "source" field meant to be a stable, citable provenance record.
    ECB is a single named central bank - for USD/INR/EUR specifically,
    confirmed (Phase 6 research) that pinning to ECB returns identical
    values to the default blend anyway, so this costs nothing and buys
    a cleaner citation.

    Chosen for this project: free, no API key, no request quotas (only
    abuse-prevention throttling), open source. Real limitations, stated
    plainly: ~30 currencies total (fine for USD/INR/EUR, would matter for
    an exotic currency), end-of-day rates only (fine for a scheduled
    daily batch, not for a hypothetical live-rate feature), no formal
    SLA (mitigated by the project being self-hostable if the public
    instance ever became unreliable).
    """

    BASE_URL = "https://api.frankfurter.dev/v1"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0)

    def __enter__(self) -> "FrankfurterProvider":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_rate(self, base: str, quote: str, as_of: date) -> Rate:
        url = f"{self.BASE_URL}/{as_of.isoformat()}"
        try:
            response = self._client.get(
                url, params={"base": base, "symbols": quote, "providers": "ECB"}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExchangeRateProviderError(
                f"Frankfurter request failed for {base}->{quote} as of {as_of}: {exc}"
            ) from exc

        payload: dict[str, Any] = response.json()
        rates = payload.get("rates", {})
        if quote not in rates:
            raise ExchangeRateProviderError(
                f"Frankfurter response for {base}->{quote} did not include {quote}: {payload}"
            )

        # Converting the JSON float via str() first, not Decimal(float)
        # directly - a raw float->Decimal conversion preserves binary
        # floating-point imprecision (Decimal(95.43) has ~15 spurious
        # trailing digits), which str() first avoids entirely.
        return Rate(
            base=base,
            quote=quote,
            rate=Decimal(str(rates[quote])),
            as_of_date=date.fromisoformat(payload["date"]),
            source="Frankfurter API (ECB reference rate)",
        )
