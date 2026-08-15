"""Tax bracket math tests. Several of these use the real US 2026 federal
brackets seeded in Phase 2, deliberately - matching a real, checkable
bracket schedule rather than an abstract synthetic one makes the hand
math directly comparable to what the IRS itself publishes.

US 2026 single-filer income tax brackets (from app/reference_data/seed.py):
  [0, 12400)      10%
  [12400, 50400)  12%
  [50400, 105700) 22%
  [105700, 201775) 24%
  [201775, 256225) 32%
  [256225, 640600) 35%
  [640600, None)  37%
"""

from decimal import Decimal

from app.compensation.services.tax import BracketDefinition, calculate_progressive_tax
from app.reference_data.models import TaxComponent


def income_tax_bracket(lower: str, upper: str | None, rate: str) -> BracketDefinition:
    return BracketDefinition(
        TaxComponent.INCOME_TAX,
        Decimal(lower),
        None if upper is None else Decimal(upper),
        Decimal(rate),
    )


US_2026_BRACKETS = [
    income_tax_bracket("0", "12400", "0.10"),
    income_tax_bracket("12400", "50400", "0.12"),
    income_tax_bracket("50400", "105700", "0.22"),
    income_tax_bracket("105700", "201775", "0.24"),
    income_tax_bracket("201775", "256225", "0.32"),
    income_tax_bracket("256225", "640600", "0.35"),
    income_tax_bracket("640600", None, "0.37"),
]


def test_zero_income_produces_zero_tax_with_no_special_casing() -> None:
    result = calculate_progressive_tax(Decimal("0"), US_2026_BRACKETS)

    assert result.total_tax_amount == Decimal("0.00")
    assert all(c.tax_amount == Decimal("0.00") for c in result.contributions)


def test_negative_income_clamps_to_zero_without_a_special_case() -> None:
    result = calculate_progressive_tax(Decimal("-500"), US_2026_BRACKETS)
    assert result.total_tax_amount == Decimal("0.00")


def test_income_exactly_at_boundary_taxed_entirely_at_lower_rate() -> None:
    """$12,400 exactly: IRS's own wording is '10% for incomes of $12,400 or
    less' - the boundary value belongs to the lower bracket in full.
    Hand math: 12400 * 10% = 1240.00, and the 12% bracket contributes 0.
    """
    result = calculate_progressive_tax(Decimal("12400.00"), US_2026_BRACKETS)

    assert result.total_tax_amount == Decimal("1240.00")
    bracket_10pct, bracket_12pct = result.contributions[0], result.contributions[1]
    assert bracket_10pct.tax_amount == Decimal("1240.00")
    assert bracket_12pct.taxable_amount == Decimal("0.00")
    assert bracket_12pct.tax_amount == Decimal("0.00")


def test_income_above_boundary_taxes_the_excess_at_the_higher_rate() -> None:
    """$12,500: $100 above the boundary. Hand math: 12400*10% = 1240.00
    from bracket 1, plus (12500-12400)*12% = 100*0.12 = 12.00 from
    bracket 2. Total 1252.00.
    """
    result = calculate_progressive_tax(Decimal("12500.00"), US_2026_BRACKETS)

    assert result.total_tax_amount == Decimal("1252.00")
    assert result.contributions[0].tax_amount == Decimal("1240.00")
    assert result.contributions[1].taxable_amount == Decimal("100.00")
    assert result.contributions[1].tax_amount == Decimal("12.00")


def test_income_spanning_many_brackets() -> None:
    """$300,000, spanning 6 of the 7 brackets (into the 32% bracket, not
    reaching the 35%/37% brackets). Hand math, bracket by bracket:
      [0,12400)      12400          * 10% = 1240.00
      [12400,50400)  38000          * 12% = 4560.00
      [50400,105700) 55300          * 22% = 12166.00
      [105700,201775) 96075         * 24% = 23058.00
      [201775,256225) 54450         * 32% = 17424.00
      [256225,640600) 300000-256225 = 43775 * 35% = 15321.25
      [640600, None)  0 (income doesn't reach this bracket)
    Sum: 1240 + 4560 + 12166 + 23058 + 17424 + 15321.25 = 73769.25
    """
    result = calculate_progressive_tax(Decimal("300000.00"), US_2026_BRACKETS)

    expected_per_bracket = [
        Decimal("1240.00"),
        Decimal("4560.00"),
        Decimal("12166.00"),
        Decimal("23058.00"),
        Decimal("17424.00"),
        Decimal("15321.25"),
        Decimal("0.00"),
    ]
    actual_per_bracket = [c.tax_amount for c in result.contributions]
    assert actual_per_bracket == expected_per_bracket
    assert result.total_tax_amount == Decimal("73769.25")


def test_income_in_unbounded_top_bracket() -> None:
    """$1,000,000, well into the unbounded 37% top bracket.
    Hand math for the first 6 brackets is identical in structure to the
    $300k case but the top two brackets now both contribute:
      [0,12400)       12400          * 10% = 1240.00
      [12400,50400)   38000          * 12% = 4560.00
      [50400,105700)  55300          * 22% = 12166.00
      [105700,201775) 96075          * 24% = 23058.00
      [201775,256225) 54450          * 32% = 17424.00
      [256225,640600) 384375         * 35% = 134531.25
      [640600, None)  1000000-640600 = 359400 * 37% = 132978.00
    Sum: 1240 + 4560 + 12166 + 23058 + 17424 + 134531.25 + 132978
       = 325957.25
    """
    result = calculate_progressive_tax(Decimal("1000000.00"), US_2026_BRACKETS)

    top_bracket = result.contributions[-1]
    assert top_bracket.upper_bound is None
    assert top_bracket.taxable_amount == Decimal("359400.00")
    assert top_bracket.tax_amount == Decimal("132978.00")
    assert result.total_tax_amount == Decimal("325957.25")


def test_bracket_order_in_input_does_not_affect_the_total() -> None:
    shuffled = [US_2026_BRACKETS[3], US_2026_BRACKETS[0], US_2026_BRACKETS[6], US_2026_BRACKETS[1]]
    remaining = [US_2026_BRACKETS[2], US_2026_BRACKETS[4], US_2026_BRACKETS[5]]

    ordered_result = calculate_progressive_tax(Decimal("300000.00"), US_2026_BRACKETS)
    shuffled_result = calculate_progressive_tax(Decimal("300000.00"), shuffled + remaining)

    assert shuffled_result.total_tax_amount == ordered_result.total_tax_amount
    # Output is still sorted ascending regardless of input order.
    output_lower_bounds = [c.lower_bound for c in shuffled_result.contributions]
    assert output_lower_bounds == sorted(output_lower_bounds)


def test_income_entirely_within_a_zero_rate_bracket() -> None:
    """India new regime FY2026-27's first bracket is 0% up to Rs400,000 -
    a real seeded example of non-zero income producing zero tax, not a
    synthetic edge case.
    """
    india_brackets = [
        income_tax_bracket("0", "400000", "0"),
        income_tax_bracket("400000", "800000", "0.05"),
    ]
    result = calculate_progressive_tax(Decimal("300000.00"), india_brackets)

    assert result.total_tax_amount == Decimal("0.00")
