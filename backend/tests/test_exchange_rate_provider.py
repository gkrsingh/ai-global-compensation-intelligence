"""Adapter tests against recorded/mocked HTTP responses only - never a
live call to the real Frankfurter API in the automated suite. The mocked
payloads below are shaped exactly like real responses captured during
Phase 6 research (USD->INR 95.43, USD->EUR 0.86453, as of 2026-08-14),
not invented numbers.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.reference_data.exchange_rate_provider import (
    ExchangeRateProviderError,
    FrankfurterProvider,
    Rate,
)


def _client_with_handler(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_rate_parses_a_successful_response_and_sends_the_expected_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/2026-08-14"
        assert request.url.params["base"] == "USD"
        assert request.url.params["symbols"] == "INR"
        assert request.url.params["providers"] == "ECB"
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-08-14", "rates": {"INR": 95.43}},
        )

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    rate = provider.get_rate("USD", "INR", date(2026, 8, 14))

    assert rate == Rate(
        base="USD",
        quote="INR",
        rate=Decimal("95.43"),
        as_of_date=date(2026, 8, 14),
        source="Frankfurter API (ECB reference rate)",
    )


def test_get_rate_uses_the_responses_actual_date_not_the_requested_date() -> None:
    """Confirmed empirically against the real API during Phase 6 research:
    requesting a Saturday (2026-08-15) returned Friday's rate
    (2026-08-14) - the response's own "date" field is the only reliable
    source of truth for which date a rate actually applies to.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-08-14", "rates": {"INR": 95.43}},
        )

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    rate = provider.get_rate("USD", "INR", date(2026, 8, 15))

    assert rate.as_of_date == date(2026, 8, 14)


def test_get_rate_converts_the_json_float_to_a_clean_decimal() -> None:
    """A raw float->Decimal conversion preserves binary floating-point
    imprecision (Decimal(0.86453) picks up ~15 spurious trailing digits) -
    proving the string round-trip actually avoids that, not just
    asserting it should.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-08-14", "rates": {"EUR": 0.86453}},
        )

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    rate = provider.get_rate("USD", "EUR", date(2026, 8, 14))

    assert rate.rate == Decimal("0.86453")
    assert str(rate.rate) == "0.86453"
    assert Decimal(0.86453) != rate.rate  # the naive conversion this deliberately avoids


def test_get_rate_raises_on_a_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error")

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    with pytest.raises(ExchangeRateProviderError):
        provider.get_rate("USD", "INR", date(2026, 8, 14))


def test_get_rate_raises_when_the_requested_currency_is_missing_from_the_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"amount": 1.0, "base": "USD", "date": "2026-08-14", "rates": {}}
        )

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    with pytest.raises(ExchangeRateProviderError):
        provider.get_rate("USD", "XYZ", date(2026, 8, 14))


def test_get_rate_raises_on_a_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    with pytest.raises(ExchangeRateProviderError):
        provider.get_rate("USD", "INR", date(2026, 8, 14))


def test_get_rate_raises_cleanly_on_a_timeout_not_a_hang_or_bare_httpx_error() -> None:
    """Phase 9's external-call resilience audit, applied to the one
    provider that already had an explicit timeout (timeout=10.0 in
    FrankfurterProvider.__init__) since Phase 6 - confirming the existing
    `except httpx.HTTPError` clause (httpx.ReadTimeout is a subclass)
    genuinely produces a clean ExchangeRateProviderError rather than
    assuming it does because the except type "should" cover it.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated stalled response", request=request)

    provider = FrankfurterProvider(client=_client_with_handler(handler))
    with pytest.raises(ExchangeRateProviderError):
        provider.get_rate("USD", "INR", date(2026, 8, 14))


def test_provider_is_usable_as_a_context_manager_and_closes_its_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-08-14", "rates": {"INR": 95.43}},
        )

    client = _client_with_handler(handler)
    with FrankfurterProvider(client=client) as provider:
        provider.get_rate("USD", "INR", date(2026, 8, 14))

    assert client.is_closed
