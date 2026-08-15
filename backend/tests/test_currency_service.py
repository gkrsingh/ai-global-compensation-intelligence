from decimal import Decimal

import pytest

from app.compensation.services.currency import MissingExchangeRateError, convert_amount


def test_same_currency_is_a_passthrough_no_rate_needed() -> None:
    result = convert_amount(Decimal("1000.00"), "USD", "USD", rates={})
    assert result == Decimal("1000.00")


def test_direct_rate_lookup() -> None:
    rates = {("USD", "INR"): Decimal("83.00000000")}
    result = convert_amount(Decimal("100.00"), "USD", "INR", rates=rates)
    assert result == Decimal("8300.00")


def test_inverse_rate_lookup_when_only_direct_pair_is_seeded() -> None:
    rates = {("USD", "INR"): Decimal("83.00000000")}
    result = convert_amount(Decimal("8300.00"), "INR", "USD", rates=rates)
    assert result == Decimal("100.00")


def test_missing_rate_raises_with_both_currencies_named() -> None:
    with pytest.raises(MissingExchangeRateError) as exc_info:
        convert_amount(Decimal("100.00"), "INR", "EUR", rates={("USD", "INR"): Decimal("83")})

    assert exc_info.value.from_currency == "INR"
    assert exc_info.value.to_currency == "EUR"


def test_does_not_triangulate_through_a_third_currency() -> None:
    """INR -> EUR is not derivable from USD-anchored rates alone - this
    must fail loudly, not silently chain INR -> USD -> EUR.
    """
    rates = {
        ("USD", "INR"): Decimal("83.00000000"),
        ("USD", "EUR"): Decimal("0.92000000"),
    }
    with pytest.raises(MissingExchangeRateError):
        convert_amount(Decimal("1000.00"), "INR", "EUR", rates=rates)


def test_rounds_half_up_not_bankers_rounding() -> None:
    """0.125 at 2 decimal places: ROUND_HALF_UP gives 0.13; Python's Decimal
    default (ROUND_HALF_EVEN) would give 0.12. Must match hand-calculation,
    not Python's default.
    """
    rates = {("USD", "XXX"): Decimal("1.25")}
    result = convert_amount(Decimal("0.1"), "USD", "XXX", rates=rates)
    assert result == Decimal("0.13")


def test_respects_target_currency_decimal_places() -> None:
    rates = {("USD", "JPY"): Decimal("150.456")}
    result = convert_amount(Decimal("10"), "USD", "JPY", rates=rates, decimal_places=0)
    assert result == Decimal("1505")


def test_zero_amount_converts_to_zero() -> None:
    rates = {("USD", "INR"): Decimal("83.00000000")}
    result = convert_amount(Decimal("0"), "USD", "INR", rates=rates)
    assert result == Decimal("0.00")
