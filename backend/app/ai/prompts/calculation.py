"""Builds the grounded context and user prompt for AI-generated insight
on a single Calculation.

`build_calculation_context` extracts every number and label the prompt
is allowed to reference - nothing else. `render_calculation_prompt` turns
that context into the exact text sent to the model. The same context
dict returned here is ALSO what gets persisted as
AIAnalysisRequest.context (step 5) and handed to the numeric-consistency
checker (step 4) as its source of truth - one extraction, two consumers,
so the checker can never drift from what the model actually saw.

Two percentages here (effective_tax_rate_percent, take_home_percent)
don't exist anywhere on Calculation itself - they're computed HERE, in
Python, specifically so the model never has to. This is the concrete
answer to "what counts as the AI inventing a number": if a ratio would
be useful in the prose, it must already exist as a plain number in this
context before the prompt is ever sent, never left for the model to
derive by dividing two other numbers itself.
"""

from decimal import Decimal
from typing import Any

from app.compensation.models import Calculation
from app.compensation.services.money import quantize_amount

_COMPONENT_TYPE_LABELS: dict[str, str] = {
    "base": "Base salary",
    "bonus": "Bonus",
    "equity": "Equity",
    "benefit": "Benefit",
    "allowance": "Allowance",
}

_TAX_COMPONENT_LABELS: dict[str, str] = {
    "income_tax": "Income tax",
    "social_security": "Social security",
    "medicare": "Medicare",
    "medicare_additional_surtax": "Medicare additional surtax",
}


def _percent(numerator: Decimal, denominator: Decimal) -> str:
    if denominator == 0:
        return "0.00"
    return str(quantize_amount(numerator / denominator * 100, 2))


def _money(amount: str) -> str:
    """breakdown["components"][i]["original_amount"] is the raw,
    unquantized Decimal captured from the user's original request input
    (e.g. "150000", not "150000.00") - never round-tripped through a
    Numeric(14,2) column the way every other figure here has been. The
    frontend has always silently normalized this via its own currency
    formatter; this prompt has no such safety net; and step 4's checker
    needs one consistent string shape per real number, not the same
    figure appearing as both "150000" and "150000.00" depending on
    which field it came from. Quantizing here, once, fixes both.
    """
    return str(quantize_amount(Decimal(amount), 2))


def build_calculation_context(calculation: Calculation) -> dict[str, Any]:
    breakdown = calculation.breakdown
    comp_input = calculation.compensation_input
    target_currency = comp_input.target_currency.code

    context: dict[str, Any] = {
        "kind": "calculation",
        "country_name": comp_input.country.name,
        "country_code": comp_input.country.code,
        "target_currency": target_currency,
        "as_of_date": comp_input.as_of_date.isoformat(),
        "regime": comp_input.regime,
        "filing_status": comp_input.filing_status,
        "components": [
            {
                "type_label": _COMPONENT_TYPE_LABELS.get(c["type"], c["type"]),
                "description": c["description"],
                "original_amount": _money(c["original_amount"]),
                "original_currency": c["original_currency"],
                "converted_amount": c["converted_amount"],
            }
            for c in breakdown["components"]
        ],
        "gross_amount": str(calculation.gross_amount),
        "total_compensation_amount": str(calculation.total_compensation_amount),
        "tax_available": calculation.total_tax_amount is not None,
    }

    if calculation.total_tax_amount is not None and calculation.net_amount is not None:
        tax_section = breakdown["tax"]
        context.update(
            {
                "total_tax_amount": str(calculation.total_tax_amount),
                "net_amount": str(calculation.net_amount),
                "effective_tax_rate_percent": _percent(
                    calculation.total_tax_amount, calculation.gross_amount
                ),
                "take_home_percent": _percent(calculation.net_amount, calculation.gross_amount),
                "tax_currency": tax_section["currency"],
                "standard_deduction": tax_section["standard_deduction"],
                "tax_components": [
                    {
                        "label": _TAX_COMPONENT_LABELS.get(tc["component"], tc["component"]),
                        "total_tax": tc["total_tax"],
                    }
                    for tc in tax_section["components"]
                ],
            }
        )

    return context


def render_calculation_prompt(context: dict[str, Any]) -> str:
    target_currency = context["target_currency"]
    lines = [
        "DATA:",
        f"Country: {context['country_name']} ({context['country_code']})",
        f"Target currency: {target_currency}",
        f"As of date: {context['as_of_date']}",
    ]
    if context.get("regime"):
        lines.append(f"Tax regime: {context['regime']}")
    if context.get("filing_status"):
        lines.append(f"Filing status: {context['filing_status']}")

    lines.append("")
    lines.append("Compensation components:")
    for c in context["components"]:
        desc = f" ({c['description']})" if c.get("description") else ""
        lines.append(
            f"- {c['type_label']}{desc}: {c['original_amount']} {c['original_currency']}"
            f" (converted: {c['converted_amount']} {target_currency})"
        )

    lines.append("")
    lines.append("Totals:")
    lines.append(f"- Gross compensation: {context['gross_amount']} {target_currency}")
    lines.append(
        "- Total compensation (including equity & benefits): "
        f"{context['total_compensation_amount']} {target_currency}"
    )

    if context["tax_available"]:
        lines.append(f"- Total tax: {context['total_tax_amount']} {target_currency}")
        lines.append(
            f"- Net compensation (after tax): {context['net_amount']} {target_currency}"
        )
        lines.append(f"- Effective tax rate: {context['effective_tax_rate_percent']}%")
        lines.append(f"- Take-home percentage of gross: {context['take_home_percent']}%")

        lines.append("")
        tax_currency = context["tax_currency"]
        if tax_currency != target_currency:
            lines.append(
                f"Tax breakdown (figures below are in {tax_currency}, the currency this "
                f"country's tax law is denominated in - NOT {target_currency}):"
            )
        else:
            lines.append("Tax breakdown:")
        if context.get("standard_deduction") is not None:
            lines.append(f"- Standard deduction: {context['standard_deduction']} {tax_currency}")
        for tc in context["tax_components"]:
            lines.append(f"- {tc['label']}: {tc['total_tax']} {tax_currency}")
    else:
        lines.append("- Tax: not available (no matching tax rule set for this country/date)")

    lines.append("")
    lines.append(
        "TASK: Write a short (3-5 sentence) plain-language explanation of this compensation "
        "offer, suitable for someone preparing to think about or discuss it in a negotiation. "
        "Focus on what the numbers mean in practice (for example, how much of the gross "
        "actually reaches take-home pay, and why). Do not make any claim about whether this is "
        "a good or competitive offer relative to the market - only explain the figures given "
        "above."
    )

    return "\n".join(lines)
