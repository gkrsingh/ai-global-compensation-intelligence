"""Adapter for the US BLS Occupational Employment and Wage Statistics
(OEWS) public timeseries API.

Everything encoded here was verified against the real API and against
BLS's own published code files during Phase 10 research, not assumed:

- The v1 endpoint needs NO registration key. v2 does, but v1 is
  sufficient for this project's volume, so OEWS adds no new secret.
- v1 caps a request at 25 series - confirmed by sending 30 and getting
  back "Requested Series list has been reduced to the system-allowed
  limit of 25 series." One occupation costs 7 series here, comfortably
  inside the cap.
- The series-ID layout below was confirmed against BLS's own oe.series
  file rather than reconstructed from memory. An initial guess at these
  IDs returned no data and the IDs turned out to be correct - the actual
  problem was the YEAR (see _LATEST_YEARS_WINDOW).
- Datatype codes come from BLS's oe.datatype file verbatim.

http_client is the injection point for tests, mirroring
FrankfurterProvider and the AI providers exactly: the automated suite
never makes a live call to BLS.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.market_data.providers.base import (
    MarketDataProvider,
    MarketDataProviderError,
    OccupationWages,
)

# Explicit and bounded, per Phase 9's external-call resilience audit -
# never left to a library default.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

# OEWS series ID = OE + seasonal(1) + areatype(1) + area(7) + industry(6)
#                     + occupation(6) + datatype(2)
_PREFIX = "OE"
_SEASONAL = "U"  # OEWS is published not-seasonally-adjusted only.
_NATIONAL_AREATYPE = "N"
_NATIONAL_AREA = "0000000"
# "Cross-Industry, Private, Federal, State, and Local" - the all-industry
# total, per BLS's oe.industry file. NOT 000001, which is private
# ownership only and would silently exclude public-sector employment.
_ALL_INDUSTRIES = "000000"

# From BLS's oe.datatype file, verbatim. Annual figures are used rather
# than hourly because this project reasons in annual compensation
# throughout.
_DATATYPES: dict[str, str] = {
    "employment_count": "01",
    "mean_value": "04",
    "percentile_10": "11",
    "percentile_25": "12",
    "percentile_50": "13",
    "percentile_75": "14",
    "percentile_90": "15",
}

# OEWS series carry only the current vintage (begin_year == end_year),
# and that vintage advances roughly annually. Rather than pin a year that
# would silently go stale, request a rolling window and keep whatever
# latest year actually comes back. v1 allows a 20-year span; a short
# window is enough and keeps responses small.
_LATEST_YEARS_WINDOW = 3

_API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"


class BlsOewsProvider(MarketDataProvider):
    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        current_year: int | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT)
        # Injectable purely so tests aren't coupled to the real clock;
        # production passes nothing and uses today's year.
        self._current_year = current_year

    @property
    def name(self) -> str:
        return "bls_oews"

    @property
    def taxonomy(self) -> str:
        # OEWS is keyed by the 2018 Standard Occupational Classification.
        return "SOC-2018"

    def _series_id(self, occupation_code: str, datatype: str) -> str:
        return (
            f"{_PREFIX}{_SEASONAL}{_NATIONAL_AREATYPE}{_NATIONAL_AREA}"
            f"{_ALL_INDUSTRIES}{occupation_code}{datatype}"
        )

    def _year_range(self) -> tuple[int, int]:
        if self._current_year is not None:
            end = self._current_year
        else:
            from datetime import date

            end = date.today().year
        return end - _LATEST_YEARS_WINDOW, end

    def fetch_national_wages(self, external_code: str) -> OccupationWages:
        series_by_field = {
            field: self._series_id(external_code, datatype)
            for field, datatype in _DATATYPES.items()
        }
        start_year, end_year = self._year_range()

        try:
            response = self._client.post(
                _API_URL,
                json={
                    "seriesid": list(series_by_field.values()),
                    "startyear": str(start_year),
                    "endyear": str(end_year),
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(
                f"BLS OEWS request failed for occupation {external_code}: {exc}"
            ) from exc

        payload: dict[str, Any] = response.json()
        # The API returns HTTP 200 even for a rejected request, reporting
        # the real outcome in this body field - so status must be checked
        # explicitly rather than relying on raise_for_status alone.
        if payload.get("status") != "REQUEST_SUCCEEDED":
            raise MarketDataProviderError(
                f"BLS OEWS reported an unsuccessful request for occupation "
                f"{external_code}: {payload.get('status')!r} {payload.get('message')!r}"
            )

        latest_by_series = self._latest_datapoint_by_series(payload)
        reference_year = max(
            (year for year, _ in latest_by_series.values()),
            default=end_year,
        )

        values: dict[str, Decimal | None] = {}
        for field, series_id in series_by_field.items():
            entry = latest_by_series.get(series_id)
            # Only accept a figure from the newest vintage present. A
            # stale year lingering on one series must never be silently
            # mixed into an otherwise-current distribution.
            values[field] = entry[1] if entry is not None and entry[0] == reference_year else None

        employment = values.pop("employment_count", None)
        label = self._series_title(payload, series_by_field["percentile_50"]) or external_code

        return OccupationWages(
            external_code=external_code,
            external_label=label,
            reference_year=reference_year,
            employment_count=int(employment) if employment is not None else None,
            **values,
        )

    @staticmethod
    def _latest_datapoint_by_series(
        payload: dict[str, Any],
    ) -> dict[str, tuple[int, Decimal]]:
        """Newest (year, value) per series, skipping anything unparseable.

        BLS uses placeholder strings for suppressed estimates rather than
        omitting the datapoint, so a non-numeric value is an ordinary
        "not published" outcome, not a malformed response - it maps to a
        missing figure, never to zero.
        """
        result: dict[str, tuple[int, Decimal]] = {}
        for series in payload.get("Results", {}).get("series", []):
            series_id = series.get("seriesID")
            if not series_id:
                continue
            for datapoint in series.get("data", []):
                try:
                    year = int(datapoint.get("year"))
                    value = Decimal(str(datapoint.get("value")).replace(",", ""))
                except (TypeError, ValueError, InvalidOperation):
                    continue
                existing = result.get(series_id)
                if existing is None or year > existing[0]:
                    result[series_id] = (year, value)
        return result

    @staticmethod
    def _series_title(payload: dict[str, Any], series_id: str) -> str | None:
        """The occupation name as BLS itself words it.

        Preferred over any label this project could write, so the UI can
        show exactly how broad the published bucket is. Only present when
        the request asked for catalog data; absent is normal, and the
        caller falls back to the bare code.
        """
        for series in payload.get("Results", {}).get("series", []):
            if series.get("seriesID") == series_id:
                catalog = series.get("catalog") or {}
                title = catalog.get("series_title")
                return str(title) if title else None
        return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BlsOewsProvider":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
