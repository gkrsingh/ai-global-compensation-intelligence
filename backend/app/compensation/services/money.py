"""Shared money-rounding helper, used by both currency conversion and
compensation totals so the same rounding rule applies everywhere amounts
get quantized to a currency's decimal places.
"""

from decimal import ROUND_HALF_UP, Decimal


def quantize_amount(value: Decimal, decimal_places: int) -> Decimal:
    """Round `value` to `decimal_places` using ROUND_HALF_UP (the
    conventional rounding mode for money), not Python's Decimal default of
    ROUND_HALF_EVEN ("banker's rounding").
    """
    quantum = Decimal(1).scaleb(-decimal_places)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)
