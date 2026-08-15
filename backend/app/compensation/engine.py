"""The calculation engine's orchestration layer: loads data (exchange
rates, the applicable tax rule set), hands it to the pure services, and
assembles an immutable Calculation. This is the only place in the engine
that touches the database - everything it delegates to (currency, totals,
tax) is pure and DB-free, per the Phase 3 hard constraint.

Two modeling decisions, confirmed explicitly rather than left implicit:

  net_amount = gross_amount - total_tax_amount, not total_compensation -
  tax. Equity and benefits have fundamentally different tax treatment
  (RSU vesting, benefit-in-kind rules, ...) that this phase doesn't model,
  so subtracting income tax from a total that includes them would be
  actively misleading, not just imprecise.

  The standard deduction reduces the taxable base ONLY for the
  income_tax component. social_security/medicare/medicare_additional_surtax
  are computed on gross_amount directly - this matches how real payroll
  works (FICA and Seguridad Social are both computed on gross wages,
  undiminished by any income-tax deduction), not an arbitrary choice.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.compensation.models import Calculation, CompensationInput
from app.compensation.repositories import find_rate_either_direction
from app.compensation.services.tax import BracketDefinition, calculate_progressive_tax
from app.compensation.services.totals import (
    CASH_COMPONENT_TYPES,
    ComponentAmount,
    calculate_compensation_totals,
)
from app.reference_data.models import TaxComponent
from app.reference_data.queries import get_effective_tax_rule_set

ENGINE_VERSION = "1.0.0"

_INCOME_TAX_COMPONENTS = frozenset({TaxComponent.INCOME_TAX})


def _build_rates(
    session: Session, component_currencies: set[str], target_currency: str, as_of: date
) -> dict[tuple[str, str], Decimal]:
    rates: dict[tuple[str, str], Decimal] = {}
    for currency_code in component_currencies:
        if currency_code == target_currency:
            continue
        found = find_rate_either_direction(session, currency_code, target_currency, as_of)
        if found is not None:
            base, quote, rate = found
            rates[(base, quote)] = rate
    return rates


def run_calculation(session: Session, compensation_input: CompensationInput) -> Calculation:
    """Run the engine for an already-persisted CompensationInput.

    Stages (session.add) but does not commit the resulting Calculation -
    committing is the caller's job, consistent with the outermost caller
    controlling the transaction.
    """
    target_currency = compensation_input.target_currency.code
    as_of = compensation_input.as_of_date

    component_currencies = {c.currency.code for c in compensation_input.components}
    rates = _build_rates(session, component_currencies, target_currency, as_of)

    component_amounts = [
        ComponentAmount(
            component_type=c.component_type,
            amount=c.amount,
            currency=c.currency.code,
            description=c.description,
        )
        for c in compensation_input.components
    ]
    totals = calculate_compensation_totals(component_amounts, target_currency, rates)

    tax_rule_set = get_effective_tax_rule_set(
        session,
        compensation_input.country.code,
        as_of,
        regime=compensation_input.regime,
        filing_status=compensation_input.filing_status,
    )

    total_tax_amount: Decimal | None = None
    net_amount: Decimal | None = None
    tax_breakdown: list[dict[str, Any]] = []

    if tax_rule_set is not None:
        brackets_by_component: dict[TaxComponent, list[BracketDefinition]] = defaultdict(list)
        for b in tax_rule_set.tax_brackets:
            brackets_by_component[b.component].append(
                BracketDefinition(b.component, b.lower_bound, b.upper_bound, b.rate)
            )

        standard_deduction = tax_rule_set.standard_deduction or Decimal("0")
        income_tax_base = max(Decimal("0"), totals.gross_amount - standard_deduction)

        total_tax_amount = Decimal("0.00")
        for component, brackets in brackets_by_component.items():
            base = income_tax_base if component in _INCOME_TAX_COMPONENTS else totals.gross_amount
            result = calculate_progressive_tax(base, brackets)
            total_tax_amount += result.total_tax_amount
            tax_breakdown.append(
                {
                    "component": component.value,
                    "taxable_base": str(base),
                    "total_tax": str(result.total_tax_amount),
                    "brackets": [
                        {
                            "lower_bound": str(c.lower_bound),
                            "upper_bound": (
                                str(c.upper_bound) if c.upper_bound is not None else None
                            ),
                            "rate": str(c.rate),
                            "taxable_amount": str(c.taxable_amount),
                            "tax_amount": str(c.tax_amount),
                        }
                        for c in result.contributions
                    ],
                }
            )

        net_amount = totals.gross_amount - total_tax_amount

    breakdown: dict[str, Any] = {
        "target_currency": target_currency,
        "as_of_date": as_of.isoformat(),
        "rates_used": {f"{b}->{q}": str(r) for (b, q), r in rates.items()},
        "components": [
            {
                "type": cc.component_type.value,
                "description": cc.description,
                "original_amount": str(cc.original_amount),
                "original_currency": cc.original_currency,
                "converted_amount": str(cc.converted_amount),
                "counts_toward_gross": cc.component_type in CASH_COMPONENT_TYPES,
            }
            for cc in totals.converted_components
        ],
        "tax": {
            "rule_set_id": tax_rule_set.id,
            "rule_set_name": tax_rule_set.name,
            "standard_deduction": str(tax_rule_set.standard_deduction)
            if tax_rule_set.standard_deduction is not None
            else None,
            "components": tax_breakdown,
        }
        if tax_rule_set is not None
        else None,
    }

    calculation = Calculation(
        compensation_input_id=compensation_input.id,
        engine_version=ENGINE_VERSION,
        gross_amount=totals.gross_amount,
        total_compensation_amount=totals.total_compensation_amount,
        tax_rule_set_id=tax_rule_set.id if tax_rule_set is not None else None,
        total_tax_amount=total_tax_amount,
        net_amount=net_amount,
        breakdown=breakdown,
    )
    session.add(calculation)
    return calculation
