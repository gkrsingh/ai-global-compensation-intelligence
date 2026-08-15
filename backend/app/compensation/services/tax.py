"""Progressive tax bracket math — pure math only, same no-I/O constraint as
currency.py and totals.py. This is the single most error-prone part of the
whole engine (see the module-level notes in tests/test_tax_service.py for
the worked examples this was checked against).

Scope, deliberately narrow: this operates on ONE list of brackets and ONE
income figure. It has no idea whether those brackets are income_tax,
social_security, or anything else - that's exactly what makes it
country-agnostic, per the Phase 3 hard constraint that the engine never
branches on country. It does not apply standard deductions and does not
combine multiple components into a final net figure; both are step 5's
orchestration, not this module's job.

Bracket boundary convention (confirmed against Phase 2's real seed data,
not invented): a bracket's upper_bound is where the NEXT bracket's rate
takes over, but the boundary value itself is taxed at THIS (lower)
bracket's rate - matching real tax law (IRS: "10% for incomes of $12,400
or less; 12% for incomes over $12,400"). The standard layer-cake formula
below produces this automatically: max(0, min(income, upper) - lower).
"""

from dataclasses import dataclass
from decimal import Decimal

from app.compensation.services.money import quantize_amount
from app.reference_data.models import TaxComponent


@dataclass(frozen=True)
class BracketDefinition:
    """One bracket, as plain data - decoupled from the SQLAlchemy ORM row
    so this module never needs a database session.
    """

    component: TaxComponent
    lower_bound: Decimal
    upper_bound: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class BracketContribution:
    component: TaxComponent
    lower_bound: Decimal
    upper_bound: Decimal | None
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


@dataclass(frozen=True)
class TaxCalculationResult:
    total_tax_amount: Decimal
    contributions: list[BracketContribution]


def calculate_progressive_tax(
    income: Decimal,
    brackets: list[BracketDefinition],
    decimal_places: int = 2,
) -> TaxCalculationResult:
    """Apply progressive bracket math to `income` over `brackets`.

    No early-return for zero/negative income - the per-bracket formula's
    max(0, ...) clamp already produces zero tax for those cases correctly,
    so a special case would be redundant, not protective.

    Brackets are sorted by lower_bound before processing, purely so the
    returned `contributions` list reads in a sensible order - the sum
    itself is order-independent (addition is commutative), so this has no
    effect on total_tax_amount.

    Rounding: each bracket's taxable amount and tax contribution are
    rounded individually, and total_tax_amount is a sum of those
    already-rounded amounts - the same round-then-sum design as totals.py,
    for the same reason (a displayed per-bracket breakdown sums exactly to
    the displayed total).
    """
    sorted_brackets = sorted(brackets, key=lambda b: b.lower_bound)
    zero = quantize_amount(Decimal(0), decimal_places)

    contributions = []
    total = zero
    for b in sorted_brackets:
        upper = income if b.upper_bound is None else b.upper_bound
        raw_taxable = max(Decimal(0), min(income, upper) - b.lower_bound)
        taxable = quantize_amount(raw_taxable, decimal_places)
        tax_for_bracket = quantize_amount(taxable * b.rate, decimal_places)

        contributions.append(
            BracketContribution(
                component=b.component,
                lower_bound=b.lower_bound,
                upper_bound=b.upper_bound,
                rate=b.rate,
                taxable_amount=taxable,
                tax_amount=tax_for_bracket,
            )
        )
        total += tax_for_bracket

    return TaxCalculationResult(total_tax_amount=total, contributions=contributions)
