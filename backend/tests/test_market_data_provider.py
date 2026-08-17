"""Adapter tests against mocked HTTP responses only - never a live call
to the real BLS API in the automated suite (the same rule as Phase 6's
exchange rate adapter and Phase 8's AI providers).

The mocked payloads below are shaped exactly like a real BLS v1 response,
captured from actual calls during Phase 10 research - not invented field
names. The real values for SOC 15-1252 (May 2025 vintage) are used
verbatim so the fixtures stay recognisable against the live source.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.market_data.providers.base import MarketDataProviderError, OccupationWages
from app.market_data.providers.bls_oews import BlsOewsProvider

# datatype suffix -> real May 2025 value for SOC 15-1252 Software Developers
_REAL_15_1252 = {
    "01": "1687890",  # employment
    "04": "148100",  # annual mean
    "11": "82460",  # 10th
    "12": "105210",  # 25th
    "13": "135980",  # median
    "14": "171980",  # 75th
    "15": "214670",  # 90th
}


# OE + U + N + area(7 zeros) + industry(6 zeros) = "OEUN" followed by 13
# zeros, then the 6-digit occupation and 2-digit datatype. Written as an
# explicit constant because getting this length wrong is exactly the bug
# that made an early version of these fixtures match nothing.
_NATIONAL_ALL_INDUSTRY_PREFIX = "OEUN" + "0" * 13


def _series_payload(
    values: dict[str, str], *, year: str = "2025", occupation: str = "151252"
) -> dict[str, Any]:
    return {
        "status": "REQUEST_SUCCEEDED",
        "responseTime": 120,
        "message": [],
        "Results": {
            "series": [
                {
                    "seriesID": f"{_NATIONAL_ALL_INDUSTRY_PREFIX}{occupation}{datatype}",
                    "data": [
                        {
                            "year": year,
                            "period": "A01",
                            "periodName": "Annual",
                            "value": value,
                            "footnotes": [{}],
                        }
                    ],
                }
                for datatype, value in values.items()
            ]
        },
    }


def _provider_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> BlsOewsProvider:
    return BlsOewsProvider(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        current_year=2026,
    )


def test_name_and_taxonomy() -> None:
    provider = _provider_with_handler(lambda request: httpx.Response(200, json={}))
    assert provider.name == "bls_oews"
    # The taxonomy is part of the interface so ingestion can select the
    # right mapping rows without hardcoding provider -> taxonomy.
    assert provider.taxonomy == "SOC-2018"


def test_fetch_parses_a_successful_response_and_requests_the_expected_series() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_series_payload(_REAL_15_1252))

    provider = _provider_with_handler(handler)
    wages = provider.fetch_national_wages("151252")

    # The series-ID layout is the single most breakable thing in this
    # adapter (an early wrong guess silently returned zero rows), so it
    # is asserted explicitly rather than only implied by the parsed result.
    assert "OEUN000000000000015125213" in captured["seriesid"]
    assert "OEUN000000000000015125211" in captured["seriesid"]
    assert len(captured["seriesid"]) == 7

    assert wages.percentile_10 == Decimal("82460")
    assert wages.percentile_25 == Decimal("105210")
    assert wages.percentile_50 == Decimal("135980")
    assert wages.percentile_75 == Decimal("171980")
    assert wages.percentile_90 == Decimal("214670")
    assert wages.mean_value == Decimal("148100")
    assert wages.employment_count == 1687890
    assert wages.reference_year == 2025
    assert wages.has_any_value is True


def test_external_label_is_none_when_the_response_carries_no_occupation_title() -> None:
    """BLS v1 returns catalog metadata (including the occupation title)
    only when asked for it, so a plain data request carries no label.
    That must surface as None so the ingestion layer can substitute its
    own verified label - degrading to the bare code here would put
    "151252" in front of a user instead of "Software Developers", which
    is exactly what running the real ingestion first revealed.
    """
    provider = _provider_with_handler(
        lambda request: httpx.Response(200, json=_series_payload(_REAL_15_1252))
    )
    wages = provider.fetch_national_wages("151252")

    assert wages.external_label is None
    assert wages.external_code == "151252"


def test_a_percentile_the_source_did_not_publish_stays_none_never_zero() -> None:
    """OEWS suppresses estimates failing its reliability screens
    (footnote 8, "Estimate not released"). A suppressed figure must reach
    the caller as None - rendering it as 0 would invent a wage of zero.
    """
    partial = {k: v for k, v in _REAL_15_1252.items() if k not in {"15", "11"}}

    provider = _provider_with_handler(
        lambda request: httpx.Response(200, json=_series_payload(partial))
    )
    wages = provider.fetch_national_wages("151252")

    assert wages.percentile_10 is None
    assert wages.percentile_90 is None
    assert wages.percentile_50 == Decimal("135980")
    assert wages.has_any_value is True


def test_a_non_numeric_placeholder_value_is_treated_as_not_published() -> None:
    """BLS returns placeholder strings for suppressed estimates rather
    than omitting the datapoint. That is an ordinary "not published"
    outcome, not a malformed response, and must not raise.
    """
    with_placeholder = {**_REAL_15_1252, "15": "-"}

    provider = _provider_with_handler(
        lambda request: httpx.Response(200, json=_series_payload(with_placeholder))
    )
    wages = provider.fetch_national_wages("151252")

    assert wages.percentile_90 is None
    assert wages.percentile_50 == Decimal("135980")


def test_a_stale_vintage_on_one_series_is_not_mixed_into_the_current_distribution() -> None:
    """The real correctness trap in this adapter: OEWS series carry one
    vintage, but a rolling year window can return an older year for a
    series that was updated on a different schedule. Splicing a 2024
    90th percentile into an otherwise-2025 distribution would produce a
    distribution that never actually existed in any published release.
    """
    payload = _series_payload({k: v for k, v in _REAL_15_1252.items() if k != "15"})
    payload["Results"]["series"].append(
        {
            "seriesID": f"{_NATIONAL_ALL_INDUSTRY_PREFIX}15125215",
            "data": [
                {
                    "year": "2024",
                    "period": "A01",
                    "periodName": "Annual",
                    "value": "999999",
                    "footnotes": [{}],
                }
            ],
        }
    )

    provider = _provider_with_handler(lambda request: httpx.Response(200, json=payload))
    wages = provider.fetch_national_wages("151252")

    assert wages.reference_year == 2025
    assert wages.percentile_90 is None  # the 2024 figure is dropped, not used
    assert wages.percentile_50 == Decimal("135980")


def test_an_occupation_with_no_published_data_returns_empty_not_an_error() -> None:
    """A code the source has nothing for is a normal result the caller
    must be able to distinguish from a failed request - the API itself
    still reports REQUEST_SUCCEEDED. Verified against the real API with
    a nonexistent code during development.
    """
    payload: dict[str, Any] = {
        "status": "REQUEST_SUCCEEDED",
        "message": ["Series does not exist for Series OEUN000000000000099999913"],
        "Results": {"series": []},
    }

    provider = _provider_with_handler(lambda request: httpx.Response(200, json=payload))
    wages = provider.fetch_national_wages("999999")

    assert isinstance(wages, OccupationWages)
    assert wages.has_any_value is False
    assert wages.percentile_50 is None


def test_fetch_raises_when_the_api_reports_an_unsuccessful_request() -> None:
    """BLS returns HTTP 200 even for a rejected request, reporting the
    real outcome in the body - so a body-level failure must be caught
    explicitly rather than trusting the status code.
    """
    payload = {"status": "REQUEST_NOT_PROCESSED", "message": ["daily threshold exceeded"]}

    provider = _provider_with_handler(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(MarketDataProviderError):
        provider.fetch_national_wages("151252")


def test_fetch_raises_on_a_non_200_response() -> None:
    provider = _provider_with_handler(lambda request: httpx.Response(500, json={}))
    with pytest.raises(MarketDataProviderError):
        provider.fetch_national_wages("151252")


def test_fetch_raises_on_a_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    provider = _provider_with_handler(handler)
    with pytest.raises(MarketDataProviderError):
        provider.fetch_national_wages("151252")


def test_fetch_raises_cleanly_on_a_timeout() -> None:
    """Phase 9's external-call resilience standard applied to this
    phase's new outbound call: a stalled request produces a clean,
    catchable error, not an unhandled httpx.ReadTimeout.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated stalled response", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(MarketDataProviderError):
        provider.fetch_national_wages("151252")


def test_provider_is_usable_as_a_context_manager_and_closes_its_client() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_series_payload(_REAL_15_1252))
        )
    )
    with BlsOewsProvider(http_client=client, current_year=2026) as provider:
        provider.fetch_national_wages("151252")

    assert client.is_closed


def test_year_range_defaults_to_the_current_calendar_year_when_not_injected() -> None:
    """current_year exists purely so tests aren't coupled to the real
    clock; production passes nothing. That default branch would otherwise
    never be exercised, leaving the only code path production actually
    uses untested.
    """
    from datetime import date

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    provider = BlsOewsProvider(http_client=httpx.Client(transport=transport))
    start, end = provider._year_range()

    assert end == date.today().year
    assert start < end


def test_a_series_entry_without_an_id_is_skipped_rather_than_crashing() -> None:
    """Defensive against a malformed response: a series block with no
    seriesID cannot be attributed to any field, so it is ignored rather
    than raising and losing the rest of a usable response.
    """
    payload = _series_payload(_REAL_15_1252)
    payload["Results"]["series"].append({"data": [{"year": "2025", "value": "1"}]})

    provider = _provider_with_handler(lambda request: httpx.Response(200, json=payload))
    wages = provider.fetch_national_wages("151252")

    assert wages.percentile_50 == Decimal("135980")
