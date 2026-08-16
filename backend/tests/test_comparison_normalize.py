"""Pure unit tests for app.comparison.services.normalize - no DB, fixed
fake rates, same discipline as test_currency.py/test_tax.py: hand-worked
numbers, not just "does it run".
"""

from decimal import Decimal

import pytest

from app.comparison.services.normalize import (
    CalculationSnapshot,
    normalize_and_compare,
)
from app.compensation.services.currency import MissingExchangeRateError


def _snapshot(
    calculation_id: int,
    source_currency: str,
    gross: str,
    total: str,
    tax: str | None,
    net: str | None,
) -> CalculationSnapshot:
    return CalculationSnapshot(
        calculation_id=calculation_id,
        source_currency=source_currency,
        gross_amount=Decimal(gross),
        total_compensation_amount=Decimal(total),
        total_tax_amount=Decimal(tax) if tax is not None else None,
        net_amount=Decimal(net) if net is not None else None,
    )


def test_same_currency_needs_no_conversion_and_reports_no_rate() -> None:
    """Both calculations are already in the comparison currency - the
    entries carry the figures through unchanged, and rate_used is None
    for both (nothing was converted, so there's no rate to report).
    """
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", "36209.00", "113791.00"),
        _snapshot(2, "USD", "120000.00", "120000.00", "20000.00", "100000.00"),
    ]

    result = normalize_and_compare(snapshots, "USD", rates={})

    assert result.entries[0].gross_amount == Decimal("150000.00")
    assert result.entries[0].rate_used is None
    assert result.entries[1].net_amount == Decimal("100000.00")
    assert result.entries[1].rate_used is None


def test_gap_analysis_picks_the_higher_offer_as_leader_with_correct_absolute_and_percent() -> None:
    """Hand math: gross 150000 vs 120000.
    gap_absolute = 150000 - 120000 = 30000.00
    gap_percent (relative to the trailing offer) = 30000 / 120000 * 100 = 25.00
    The leader's own gap against itself is 0 / 0%.
    """
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", "36209.00", "113791.00"),
        _snapshot(2, "USD", "120000.00", "120000.00", "20000.00", "100000.00"),
    ]

    result = normalize_and_compare(snapshots, "USD", rates={})

    gross_gap = result.gap_analysis["gross_amount"]
    assert gross_gap is not None
    assert gross_gap.leader_calculation_id == 1
    by_id = {g.calculation_id: g for g in gross_gap.entries}
    assert by_id[1].gap_absolute == Decimal("0.00")
    assert by_id[1].gap_percent == Decimal("0.00")
    assert by_id[2].gap_absolute == Decimal("30000.00")
    assert by_id[2].gap_percent == Decimal("25.00")


def test_cross_currency_conversion_uses_the_supplied_rate() -> None:
    """A deliberately round fixture rate (not a real fetched one) so the
    hand math is trivial: 1 USD = 90.00000000 INR.

    calc 1: USD 150000.00 gross (already in comparison currency, USD).
    calc 2: INR 9,000,000.00 gross -> 9000000 / 90 = 100000.00 USD.
    gap: leader is calc 1 (150000 > 100000), absolute = 50000.00,
    percent = 50000 / 100000 * 100 = 50.00.
    """
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", "36209.00", "113791.00"),
        _snapshot(2, "INR", "9000000.00", "9000000.00", "1500000.00", "7500000.00"),
    ]
    rates = {("USD", "INR"): Decimal("90.00000000")}

    result = normalize_and_compare(snapshots, "USD", rates=rates)

    entry_2 = next(e for e in result.entries if e.calculation_id == 2)
    assert entry_2.gross_amount == Decimal("100000.00")
    assert entry_2.net_amount == Decimal("83333.33")
    # rate_used is expressed as "1 INR = X USD" (source -> comparison
    # direction), i.e. the reciprocal of the stored USD->INR rate,
    # quantized to 8 places like every other persisted rate in this
    # project. 1/90 = 0.0111111... -> 0.01111111 (ROUND_HALF_UP).
    assert entry_2.rate_used == Decimal("0.01111111")

    gross_gap = result.gap_analysis["gross_amount"]
    assert gross_gap is not None
    assert gross_gap.leader_calculation_id == 1
    by_id = {g.calculation_id: g for g in gross_gap.entries}
    assert by_id[2].gap_absolute == Decimal("50000.00")
    assert by_id[2].gap_percent == Decimal("50.00")


def test_rate_used_reports_the_direct_rate_when_the_comparison_currency_is_the_quote() -> None:
    """The mirror image of the INR<->USD case above: when the comparison
    currency is the QUOTE side of a directly-stored rate (not the
    inverse), rate_used should be that direct rate, untouched.
    """
    snapshots = [_snapshot(1, "USD", "100.00", "100.00", None, None)]
    rates = {("USD", "INR"): Decimal("90.00000000")}

    result = normalize_and_compare(snapshots, "INR", rates=rates)

    assert result.entries[0].rate_used == Decimal("90.00000000")
    assert result.entries[0].gross_amount == Decimal("9000.00")


def test_missing_rate_propagates_not_swallowed() -> None:
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", None, None),
        _snapshot(2, "INR", "9000000.00", "9000000.00", None, None),
    ]

    with pytest.raises(MissingExchangeRateError):
        normalize_and_compare(snapshots, "EUR", rates={})


def test_net_amount_gap_is_none_when_any_calculation_lacks_a_tax_rule_set() -> None:
    """calc 2 has no matching tax rule set (net_amount/total_tax_amount
    both None, exactly like Calculation.net_amount for that case) - gross
    and total_compensation gap analysis still work; net_amount's does not,
    rather than silently ranking a real number against "unknown".
    """
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", "36209.00", "113791.00"),
        _snapshot(2, "USD", "120000.00", "120000.00", None, None),
    ]

    result = normalize_and_compare(snapshots, "USD", rates={})

    assert result.gap_analysis["net_amount"] is None
    assert result.gap_analysis["gross_amount"] is not None
    assert result.entries[1].net_amount is None


def test_gap_percent_is_none_when_the_trailing_amount_is_zero() -> None:
    """calc 2's net_amount is $0.00 (100% of gross went to tax - a real,
    if extreme, possibility) trailing calc 1's nonzero net_amount: the
    percent gap would divide by zero - must come back None (undefined),
    not raise or silently return 0/inf. The absolute gap is still a real
    number either way.
    """
    snapshots = [
        _snapshot(1, "USD", "1000.00", "1000.00", "500.00", "500.00"),
        _snapshot(2, "USD", "1000.00", "1000.00", "1000.00", "0.00"),
    ]

    result = normalize_and_compare(snapshots, "USD", rates={})

    net_gap = result.gap_analysis["net_amount"]
    assert net_gap is not None
    by_id = {g.calculation_id: g for g in net_gap.entries}
    assert by_id[1].gap_absolute == Decimal("0.00")
    assert by_id[1].gap_percent == Decimal("0.00")
    assert by_id[2].gap_absolute == Decimal("500.00")
    assert by_id[2].gap_percent is None


def test_total_tax_amount_is_converted_and_shown_but_excluded_from_gap_analysis() -> None:
    """total_tax_amount appears on each entry (for display) but is
    deliberately not one of GAP_METRICS - "ahead" for tax means lowest,
    the opposite polarity of gross/total/net, so it's excluded from the
    highest-wins leader logic rather than silently mislabeling the
    lowest-tax offer as "behind".
    """
    snapshots = [
        _snapshot(1, "USD", "150000.00", "150000.00", "36209.00", "113791.00"),
        _snapshot(2, "USD", "120000.00", "120000.00", "5000.00", "115000.00"),
    ]

    result = normalize_and_compare(snapshots, "USD", rates={})

    assert result.entries[0].total_tax_amount == Decimal("36209.00")
    assert "total_tax_amount" not in result.gap_analysis
