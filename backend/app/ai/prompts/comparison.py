"""Builds the grounded context and user prompt for AI-generated insight
on a Comparison. Unlike calculation.py, no new numbers get computed here
at all - Phase 7's Comparison.result already carries every converted
figure and every gap_absolute/gap_percent this needs, so this module is
purely re-shaping already-grounded data into prompt text, never deriving
anything new.
"""

from typing import Any

from app.comparison.models import Comparison

_METRIC_LABELS: dict[str, str] = {
    "gross_amount": "Gross compensation",
    "total_compensation_amount": "Total compensation",
    "net_amount": "Net compensation",
}
# Same order every time, regardless of dict insertion order in the
# stored JSONB - a stable prompt for a stable set of inputs.
_METRIC_ORDER: tuple[str, ...] = ("gross_amount", "total_compensation_amount", "net_amount")


def build_comparison_context(comparison: Comparison) -> dict[str, Any]:
    result: dict[str, Any] = comparison.result
    return {
        "kind": "comparison",
        "name": comparison.name,
        "comparison_currency": comparison.comparison_currency.code,
        "as_of_date": comparison.as_of_date.isoformat(),
        "entries": result["entries"],
        "gap_analysis": result["gap_analysis"],
    }


def render_comparison_prompt(context: dict[str, Any]) -> str:
    entries = context["entries"]
    currency = context["comparison_currency"]
    offer_label_by_id = {e["calculation_id"]: f"Offer {i + 1}" for i, e in enumerate(entries)}

    lines = [
        "DATA:",
        f"Comparison name: {context['name']}",
        f"Compared in: {currency}",
        f"As of date: {context['as_of_date']}",
        "",
        "Offers:",
    ]
    for entry in entries:
        label = offer_label_by_id[entry["calculation_id"]]
        origin = (
            f"converted from {entry['source_currency']} at rate {entry['rate_used']}"
            if entry["rate_used"] is not None
            else f"originally in {entry['source_currency']}"
        )
        tax = (
            f"{entry['total_tax_amount']} {currency}"
            if entry["total_tax_amount"] is not None
            else "not available"
        )
        net = (
            f"{entry['net_amount']} {currency}"
            if entry["net_amount"] is not None
            else "not available"
        )
        lines.append(
            f"- {label} ({origin}): Gross {entry['gross_amount']} {currency}, "
            f"Total compensation {entry['total_compensation_amount']} {currency}, "
            f"Total tax {tax}, Net {net}"
        )

    lines.append("")
    lines.append("Gap analysis (which offer is ahead, and by how much):")
    for metric in _METRIC_ORDER:
        label = _METRIC_LABELS[metric]
        gap = context["gap_analysis"].get(metric)
        if gap is None:
            lines.append(f"- {label}: not available for every offer.")
            continue
        leader_id = gap["leader_calculation_id"]
        lines.append(f"- {label}: {offer_label_by_id[leader_id]} is ahead.")
        for g in gap["entries"]:
            if g["calculation_id"] == leader_id:
                continue
            offer_label = offer_label_by_id[g["calculation_id"]]
            percent = f" ({g['gap_percent']}%)" if g["gap_percent"] is not None else ""
            lines.append(f"  - {offer_label} trails by {g['gap_absolute']} {currency}{percent}")

    lines.append("")
    lines.append(
        "TASK: Write a short (3-5 sentence) plain-language summary comparing these offers, "
        "useful for someone deciding between them or preparing to negotiate. Reference the gap "
        "figures given above where relevant. Do not make any claim about whether either offer "
        "is competitive relative to the external market - only explain the figures given above."
    )

    return "\n".join(lines)
