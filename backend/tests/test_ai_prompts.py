"""Tests for the context-building and prompt-rendering functions - pure,
deterministic given an already-persisted Calculation/Comparison, so
these build REAL ones via the actual engine/orchestration code (same
discipline as test_calculation_engine.py) rather than hand-faking ORM
objects, and assert on hand-verified figures.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts.calculation import build_calculation_context, render_calculation_prompt
from app.ai.prompts.comparison import build_comparison_context, render_comparison_prompt
from app.ai.prompts.system import SYSTEM_PROMPT
from app.auth.models import User
from app.comparison.orchestration import build_comparison
from app.compensation.engine import run_calculation
from app.compensation.models import (
    Calculation,
    CompensationComponent,
    CompensationInput,
    ComponentType,
)
from app.reference_data.models import Country, Currency, ExchangeRate


def _country(db_session: Session, code: str) -> Country:
    country = db_session.scalar(select(Country).where(Country.code == code))
    assert country is not None
    return country


def _currency(db_session: Session, code: str) -> Currency:
    currency = db_session.scalar(select(Currency).where(Currency.code == code))
    assert currency is not None
    return currency


def _us_150k(db_session: Session) -> Calculation:
    """The same hand-verified US $150,000 single-filer example used
    throughout this project: net $113,791.00 (24.14% effective tax rate,
    75.86% take-home - hand math: 36209.00/150000.00*100 = 24.139333...
    -> 24.14; 113791.00/150000.00*100 = 75.860666... -> 75.86).
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="single",
        as_of_date=date.today(),
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("150000.00"), currency_id=usd.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()
    return calculation


def _india_to_eur(db_session: Session) -> Calculation:
    """The exact tax-currency-mismatch scenario from Phase 6/7: India
    Rs15,00,000 new regime, normalized to EUR. Hand math (already
    verified in Phase 6/7): tax basis stays in INR (93750.00), only the
    final total is converted. Uses a round fixture rate (0.01) rather
    than a real fetched one so the numbers stay simple and independent
    of whatever the live provider returns today.
    """
    india = _country(db_session, "IN")
    inr = _currency(db_session, "INR")
    eur = _currency(db_session, "EUR")
    today = date.today()
    db_session.add(
        ExchangeRate(
            base_currency_id=inr.id,
            quote_currency_id=eur.id,
            rate=Decimal("0.01000000"),
            as_of_date=today,
            source="test-fixture",
        )
    )
    db_session.flush()

    comp_input = CompensationInput(
        country_id=india.id, target_currency_id=eur.id, regime="new", as_of_date=today
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("1500000.00"), currency_id=inr.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()
    return calculation


def _spain_no_regime_ambiguity(db_session: Session, amount: str) -> Calculation:
    spain = _country(db_session, "ES")
    eur = _currency(db_session, "EUR")
    comp_input = CompensationInput(
        country_id=spain.id, target_currency_id=eur.id, as_of_date=date.today()
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal(amount), currency_id=eur.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()
    return calculation


def test_system_prompt_contains_the_core_constraints() -> None:
    """A lightweight guard so a future accidental edit that drops one of
    the actual safety rules gets caught immediately, not silently.
    """
    assert "Never perform arithmetic" in SYSTEM_PROMPT
    assert "verbatim in the DATA section" in SYSTEM_PROMPT
    assert "market rate" in SYSTEM_PROMPT
    assert "150K" in SYSTEM_PROMPT  # the abbreviation ban's concrete example


def test_calculation_prompt_matches_hand_verified_figures(db_session: Session) -> None:
    calculation = _us_150k(db_session)

    context = build_calculation_context(calculation)
    prompt = render_calculation_prompt(context)

    assert context["gross_amount"] == "150000.00"
    assert context["total_tax_amount"] == "36209.00"
    assert context["net_amount"] == "113791.00"
    assert context["effective_tax_rate_percent"] == "24.14"
    assert context["take_home_percent"] == "75.86"

    assert "Gross compensation: 150000.00 USD" in prompt
    assert "Total tax: 36209.00 USD" in prompt
    assert "Net compensation (after tax): 113791.00 USD" in prompt
    assert "Effective tax rate: 24.14%" in prompt
    assert "Take-home percentage of gross: 75.86%" in prompt
    assert "Standard deduction: 16100.00 USD" in prompt
    assert "Income tax: 24734.00 USD" in prompt
    assert "Social security: 9300.00 USD" in prompt


def test_calculation_prompt_flags_tax_currency_mismatch(db_session: Session) -> None:
    calculation = _india_to_eur(db_session)

    context = build_calculation_context(calculation)
    prompt = render_calculation_prompt(context)

    assert context["tax_currency"] == "INR"
    assert context["target_currency"] == "EUR"
    # Hand math: gross 1500000.00 * 0.01 = 15000.00 EUR; tax 93750.00 INR
    # * 0.01 = 937.50 EUR; net = 15000.00 - 937.50 = 14062.50 EUR.
    assert context["gross_amount"] == "15000.00"
    assert context["total_tax_amount"] == "937.50"
    assert context["net_amount"] == "14062.50"
    assert context["standard_deduction"] == "75000.00"

    assert "figures below are in INR" in prompt
    assert "NOT EUR" in prompt
    assert "Standard deduction: 75000.00 INR" in prompt
    assert "Income tax: 93750.00 INR" in prompt
    # The target-currency totals must never be silently relabeled as INR.
    assert "Gross compensation: 15000.00 EUR" in prompt


def test_calculation_prompt_original_amount_is_quantized_even_when_input_was_not(
    db_session: Session,
) -> None:
    """The real formatting bug caught while building this step: an
    unquantized in-memory Decimal (e.g. "150000", never round-tripped
    through the Numeric(14,2) column) must not leak into the prompt as
    "150000" while every other figure shows "150000.00" - one consistent
    shape per real number, or step 4's checker would see the same number
    as two different strings depending on which field it came from.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    comp_input = CompensationInput(
        country_id=us.id, target_currency_id=usd.id, filing_status="single", as_of_date=date.today()
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE,
            amount=Decimal("150000"),  # deliberately unquantized, matches real API input shape
            currency_id=usd.id,
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()

    context = build_calculation_context(calculation)

    assert context["components"][0]["original_amount"] == "150000.00"
    assert "150000.00 USD (converted: 150000.00 USD)" in render_calculation_prompt(context)


def test_calculation_prompt_shows_no_tax_data_honestly(db_session: Session) -> None:
    """filing_status="married_filing_jointly" matches no seeded US rule
    set (same fixture used in test_calculation_engine.py) - tax fields
    must be absent from context entirely, not zeroed or guessed.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="married_filing_jointly",
        as_of_date=date.today(),
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("100000.00"), currency_id=usd.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()

    context = build_calculation_context(calculation)
    prompt = render_calculation_prompt(context)

    assert context["tax_available"] is False
    assert "total_tax_amount" not in context
    assert "effective_tax_rate_percent" not in context
    assert "Tax: not available (no matching tax rule set" in prompt
    assert "Effective tax rate" not in prompt


def test_calculation_prompt_percent_is_zero_not_a_division_error_when_gross_is_zero(
    db_session: Session,
) -> None:
    """A $0 base component is a legitimate (if degenerate) input -
    CompensationComponentIn only requires amount >= 0, not > 0 - so
    gross_amount can genuinely be zero. effective_tax_rate_percent and
    take_home_percent must come back "0.00", not raise a
    ZeroDivisionError.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    comp_input = CompensationInput(
        country_id=us.id, target_currency_id=usd.id, filing_status="single", as_of_date=date.today()
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("0.00"), currency_id=usd.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calculation = run_calculation(db_session, comp_input)
    db_session.flush()

    context = build_calculation_context(calculation)

    assert context["gross_amount"] == "0.00"
    assert context["effective_tax_rate_percent"] == "0.00"
    assert context["take_home_percent"] == "0.00"


def test_comparison_prompt_matches_hand_verified_gap_figures(db_session: Session) -> None:
    """Two same-currency Spain offers (150000.00 EUR vs 100000.00 EUR) -
    deliberately both EUR so no exchange rate is needed at all (already
    covered elsewhere: test_comparison_normalize.py owns cross-currency
    conversion correctness). This test is about the comparison PROMPT's
    own rendering, so it only asserts on gross-amount gap math, which
    needs no knowledge of Spain's full tax bracket schedule to hand-
    verify: gap_absolute = 150000.00 - 100000.00 = 50000.00,
    gap_percent = 50000.00 / 100000.00 * 100 = 50.00.
    """
    calc_a = _spain_no_regime_ambiguity(db_session, "150000.00")
    calc_b = _spain_no_regime_ambiguity(db_session, "100000.00")

    user = User(email="ai-prompt-test@example.com", hashed_password="x")
    db_session.add(user)
    db_session.flush()
    # build_comparison's own scope: it doesn't run the engine, only
    # references calculations that already belong to the caller - built
    # here directly via run_calculation() (bypassing the API layer,
    # which is the only place that normally tags user_id), so these
    # need it set explicitly to pass the ownership check.
    calc_a.user_id = user.id
    calc_b.user_id = user.id
    db_session.flush()

    comparison = build_comparison(
        db_session, user, "hand-check", [calc_a.id, calc_b.id], "EUR", date.today()
    )
    db_session.flush()

    context = build_comparison_context(comparison)
    prompt = render_comparison_prompt(context)

    gross_gap = context["gap_analysis"]["gross_amount"]
    assert gross_gap["leader_calculation_id"] == calc_a.id
    trailing = next(e for e in gross_gap["entries"] if e["calculation_id"] == calc_b.id)
    assert trailing["gap_absolute"] == "50000.00"
    assert trailing["gap_percent"] == "50.00"

    assert "Offer 1 (originally in EUR): Gross 150000.00 EUR" in prompt
    assert "Offer 2 (originally in EUR): Gross 100000.00 EUR" in prompt
    assert "Gross compensation: Offer 1 is ahead." in prompt
    assert "Offer 2 trails by 50000.00 EUR (50.00%)" in prompt

    db_session.delete(comparison)
    db_session.delete(user)


def test_comparison_prompt_shows_not_available_for_a_missing_metric(db_session: Session) -> None:
    """calc_a matches no US tax rule set (net_amount is None, same
    fixture as test_calculation_prompt_shows_no_tax_data_honestly) -
    net_amount's gap analysis must be None for the whole comparison, not
    silently computed from only the one offer that has it.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="married_filing_jointly",
        as_of_date=date.today(),
    )
    comp_input.components.append(
        CompensationComponent(
            component_type=ComponentType.BASE, amount=Decimal("100000.00"), currency_id=usd.id
        )
    )
    db_session.add(comp_input)
    db_session.flush()
    calc_a = run_calculation(db_session, comp_input)
    db_session.flush()

    calc_b = _us_150k(db_session)

    user = User(email="ai-prompt-test-2@example.com", hashed_password="x")
    db_session.add(user)
    db_session.flush()
    calc_a.user_id = user.id
    calc_b.user_id = user.id
    db_session.flush()

    comparison = build_comparison(
        db_session, user, "no-tax-comparison", [calc_a.id, calc_b.id], "USD", date.today()
    )
    db_session.flush()

    context = build_comparison_context(comparison)
    prompt = render_comparison_prompt(context)

    assert context["gap_analysis"]["net_amount"] is None
    assert "Net compensation: not available for every offer." in prompt

    db_session.delete(comparison)
    db_session.delete(user)
