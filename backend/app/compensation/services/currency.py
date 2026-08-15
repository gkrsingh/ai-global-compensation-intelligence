"""Currency conversion — pure math only.

No database or network access anywhere in this module, by design (see the
Phase 3 hard constraints): rates are handed in as plain data, already
loaded by a caller. This makes the actual math trivially unit-testable
with fixed/fake rates and, longer-term, keeps it reusable regardless of
where rates eventually come from (Phase 2's illustrative seed data now,
a real rate-fetching integration later).
"""

from decimal import Decimal

from app.compensation.services.money import quantize_amount


class MissingExchangeRateError(Exception):
    """No rate (direct or inverse) is available for a currency pair.

    Deliberately not resolved by chaining through a third currency (e.g.
    INR -> USD -> EUR when only USD-anchored rates exist) — triangulating
    would compound rate error silently. Better to fail loudly and let the
    caller see exactly which pair is missing.
    """

    def __init__(self, from_currency: str, to_currency: str) -> None:
        self.from_currency = from_currency
        self.to_currency = to_currency
        super().__init__(f"No exchange rate available for {from_currency} -> {to_currency}")


def convert_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rates: dict[tuple[str, str], Decimal],
    decimal_places: int = 2,
) -> Decimal:
    """Convert `amount` from `from_currency` to `to_currency`.

    `rates` maps (base_currency, quote_currency) -> rate, where the rate
    means "1 unit of base_currency = rate units of quote_currency" — the
    same base/quote convention as the ExchangeRate model. Looked up
    directly first; if only the inverse pair is present, the reciprocal is
    used instead of requiring both directions to be seeded separately.

    Result is rounded to `decimal_places` using ROUND_HALF_UP (the
    conventional rounding mode for money), not Python's Decimal default of
    ROUND_HALF_EVEN ("banker's rounding"), which would round e.g. 2.5 to 2
    instead of 3 and surprise anyone checking the math by hand.
    """
    if from_currency == to_currency:
        converted = amount
    else:
        direct_rate = rates.get((from_currency, to_currency))
        if direct_rate is not None:
            converted = amount * direct_rate
        else:
            inverse_rate = rates.get((to_currency, from_currency))
            if inverse_rate is None:
                raise MissingExchangeRateError(from_currency, to_currency)
            converted = amount / inverse_rate

    return quantize_amount(converted, decimal_places)
