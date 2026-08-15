"""Gross and total compensation — pure math only, same no-I/O constraint
as currency.py.

Definitions (confirmed explicitly, not assumed - the phase notes group
"gross/total comp" together but they're two different numbers):
  gross = cash-only: BASE + BONUS + ALLOWANCE, before tax.
  total = everything: gross's components plus EQUITY and BENEFIT at their
          stated value.

Rounding: each component is converted and rounded individually (via
currency.convert_amount, which always rounds), and gross/total are sums of
those already-rounded amounts - not full-precision sums rounded only at
the end. This means the breakdown's line items always sum exactly to the
displayed totals, which matters more here than the marginal precision
difference, especially since convert_amount already rounds by contract.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.compensation.models import ComponentType
from app.compensation.services.currency import convert_amount
from app.compensation.services.money import quantize_amount

CASH_COMPONENT_TYPES = frozenset({ComponentType.BASE, ComponentType.BONUS, ComponentType.ALLOWANCE})


@dataclass(frozen=True)
class ComponentAmount:
    """One compensation component, as plain data - decoupled from the
    SQLAlchemy ORM row so this module never needs a database session.
    """

    component_type: ComponentType
    amount: Decimal
    currency: str
    description: str | None = None


@dataclass(frozen=True)
class ConvertedComponent:
    component_type: ComponentType
    description: str | None
    original_amount: Decimal
    original_currency: str
    converted_amount: Decimal


@dataclass(frozen=True)
class CompensationTotals:
    gross_amount: Decimal
    total_compensation_amount: Decimal
    converted_components: list[ConvertedComponent]


def calculate_compensation_totals(
    components: list[ComponentAmount],
    target_currency: str,
    rates: dict[tuple[str, str], Decimal],
    decimal_places: int = 2,
) -> CompensationTotals:
    converted = [
        ConvertedComponent(
            component_type=c.component_type,
            description=c.description,
            original_amount=c.amount,
            original_currency=c.currency,
            converted_amount=convert_amount(
                c.amount, c.currency, target_currency, rates, decimal_places
            ),
        )
        for c in components
    ]

    zero = quantize_amount(Decimal(0), decimal_places)
    gross = zero
    total = zero
    for cc in converted:
        total += cc.converted_amount
        if cc.component_type in CASH_COMPONENT_TYPES:
            gross += cc.converted_amount

    return CompensationTotals(
        gross_amount=gross, total_compensation_amount=total, converted_components=converted
    )
