from decimal import Decimal

from app.compensation.models import ComponentType
from app.compensation.services.totals import ComponentAmount, calculate_compensation_totals


def test_all_cash_components_gross_equals_total() -> None:
    components = [
        ComponentAmount(ComponentType.BASE, Decimal("100000.00"), "USD"),
        ComponentAmount(ComponentType.BONUS, Decimal("10000.00"), "USD"),
        ComponentAmount(ComponentType.ALLOWANCE, Decimal("5000.00"), "USD"),
    ]
    totals = calculate_compensation_totals(components, "USD", rates={})

    assert totals.gross_amount == Decimal("115000.00")
    assert totals.total_compensation_amount == Decimal("115000.00")


def test_equity_and_benefits_count_toward_total_not_gross() -> None:
    components = [
        ComponentAmount(ComponentType.BASE, Decimal("100000.00"), "USD"),
        ComponentAmount(ComponentType.EQUITY, Decimal("50000.00"), "USD", "RSU grant"),
        ComponentAmount(ComponentType.BENEFIT, Decimal("8000.00"), "USD", "Health insurance"),
    ]
    totals = calculate_compensation_totals(components, "USD", rates={})

    assert totals.gross_amount == Decimal("100000.00")
    assert totals.total_compensation_amount == Decimal("158000.00")


def test_empty_components_gives_zero_for_both_correctly_scaled() -> None:
    totals = calculate_compensation_totals([], "USD", rates={})

    assert totals.gross_amount == Decimal("0.00")
    assert totals.total_compensation_amount == Decimal("0.00")


def test_converts_each_component_to_target_currency() -> None:
    components = [
        ComponentAmount(ComponentType.BASE, Decimal("100000.00"), "USD"),
        ComponentAmount(ComponentType.BONUS, Decimal("100000.00"), "INR"),
    ]
    rates = {("USD", "INR"): Decimal("83.00000000")}
    totals = calculate_compensation_totals(components, "USD", rates=rates)

    # 100000 INR -> USD at 83: 100000 / 83 = 1204.819277... -> 1204.82
    assert totals.gross_amount == Decimal("101204.82")
    assert len(totals.converted_components) == 2
    assert totals.converted_components[1].original_currency == "INR"
    assert totals.converted_components[1].converted_amount == Decimal("1204.82")


def test_breakdown_preserves_description_and_original_values() -> None:
    components = [ComponentAmount(ComponentType.BONUS, Decimal("5000.00"), "USD", "Signing bonus")]
    totals = calculate_compensation_totals(components, "USD", rates={})

    [line] = totals.converted_components
    assert line.description == "Signing bonus"
    assert line.original_amount == Decimal("5000.00")
    assert line.original_currency == "USD"
    assert line.component_type == ComponentType.BONUS


def test_rounds_each_component_before_summing_not_after() -> None:
    """Two components that individually round up more than their raw sum
    would: proves round-then-sum is actually implemented, not just
    documented. 1 * 0.125 = 0.125 -> rounds to 0.13 each (half-up);
    round-then-sum gives 0.26. A sum-then-round approach would sum the raw
    0.125 + 0.125 = 0.25 (already 2dp, no further rounding) and give 0.25
    instead - a genuinely different answer, not a rounding coincidence.
    """
    components = [
        ComponentAmount(ComponentType.BASE, Decimal("1"), "USD"),
        ComponentAmount(ComponentType.BONUS, Decimal("1"), "USD"),
    ]
    rates = {("USD", "XXX"): Decimal("0.125")}
    totals = calculate_compensation_totals(components, "XXX", rates=rates)

    assert totals.gross_amount == Decimal("0.26")
