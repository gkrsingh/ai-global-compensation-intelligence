"""Integration tests for the orchestration engine - these deliberately hit
the real, Phase-2-seeded database (real tax rule sets), unlike the
pure-service tests. This is the layer the hard constraint explicitly
allows to touch the DB. Exchange rates are no longer part of that seed
(Phase 6) - the one test here that needs a rate fixtures its own row.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compensation.engine import ENGINE_VERSION, run_calculation
from app.compensation.models import (
    Calculation,
    CompensationComponent,
    CompensationInput,
    ComponentType,
)
from app.compensation.services.currency import MissingExchangeRateError
from app.reference_data.models import Country, Currency, ExchangeRate


def _country(db_session: Session, code: str) -> Country:
    country = db_session.scalar(select(Country).where(Country.code == code))
    assert country is not None
    return country


def _currency(db_session: Session, code: str) -> Currency:
    currency = db_session.scalar(select(Currency).where(Currency.code == code))
    assert currency is not None
    return currency


def _component(
    component_type: ComponentType, amount: str, currency: Currency
) -> CompensationComponent:
    return CompensationComponent(
        component_type=component_type, amount=Decimal(amount), currency_id=currency.id
    )


def test_us_single_filer_base_salary_only(db_session: Session) -> None:
    """$150,000 base, US single filer, TY2026 brackets.

    Hand math:
      standard_deduction = 16100.00
      income_tax_base = 150000 - 16100 = 133900.00
      income_tax: [0,12400)*.10=1240.00 + [12400,50400)*.12=4560.00
                  + [50400,105700)*.22=12166.00
                  + (133900-105700)=28200 * .24 = 6768.00
                  (133900 doesn't reach 201775, brackets above contribute 0)
                = 1240+4560+12166+6768 = 24734.00
      social_security: base=gross=150000 (uncapped by deduction, <184500 cap)
                      = 150000 * .062 = 9300.00
      medicare: 150000 * .0145 = 2175.00
      medicare_additional_surtax: 150000 doesn't reach 200000 -> 0.00
      total_tax = 24734 + 9300 + 2175 + 0 = 36209.00
      net = 150000 - 36209 = 113791.00
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")

    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="single",
        as_of_date=date.today(),
    )
    comp_input.components.append(_component(ComponentType.BASE, "150000.00", usd))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.gross_amount == Decimal("150000.00")
    assert calculation.total_compensation_amount == Decimal("150000.00")
    assert calculation.tax_rule_set_id is not None
    assert calculation.total_tax_amount == Decimal("36209.00")
    assert calculation.net_amount == Decimal("113791.00")
    assert calculation.engine_version == ENGINE_VERSION

    # medicare_additional_surtax is included even though it contributes
    # $0.00 at this income (its bracket starts at $200,000) - the engine
    # iterates every component present in the rule set, not just the ones
    # that end up non-zero, so the breakdown shows it was checked rather
    # than silently omitted.
    by_component = {
        c["component"]: c for c in calculation.breakdown["tax"]["components"]
    }
    assert by_component.keys() == {
        "income_tax",
        "social_security",
        "medicare",
        "medicare_additional_surtax",
    }
    assert by_component["medicare_additional_surtax"]["total_tax"] == "0.00"
    assert calculation.breakdown["tax"]["standard_deduction"] == "16100.00"


def test_india_new_regime_income_entirely_in_zero_rate_bracket(db_session: Session) -> None:
    """Rs300,000 base, India new regime: entirely within the [0,400000) 0%
    bracket. No social_security/medicare-equivalent components exist for
    India in the seeded data, so income_tax is the only component.
    """
    india = _country(db_session, "IN")
    inr = _currency(db_session, "INR")

    comp_input = CompensationInput(
        country_id=india.id,
        target_currency_id=inr.id,
        regime="new",
        as_of_date=date.today(),
    )
    comp_input.components.append(_component(ComponentType.BASE, "300000.00", inr))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.total_tax_amount == Decimal("0.00")
    assert calculation.net_amount == Decimal("300000.00")
    tax_components = {c["component"] for c in calculation.breakdown["tax"]["components"]}
    assert tax_components == {"income_tax"}


def test_india_new_regime_spanning_four_brackets(db_session: Session) -> None:
    """Rs15,00,000 base, India new regime FY2026-27 - the step 6
    verification example, spanning real brackets with real tax owed
    (unlike the zero-bracket case above).

    Hand math:
      taxable_income = 1500000 - 75000 (standard deduction) = 1425000
      [0,400000)          400000 * 0%  =      0.00
      [400000,800000)     400000 * 5%  =  20000.00
      [800000,1200000)    400000 * 10% =  40000.00
      [1200000,1600000)  (1425000-1200000)=225000 * 15% = 33750.00
      [1600000, None)    1425000 doesn't reach this bracket -> 0.00
      total_tax = 0 + 20000 + 40000 + 33750 = 93750.00
      net = 1500000 - 93750 = 1406250.00
    """
    india = _country(db_session, "IN")
    inr = _currency(db_session, "INR")

    comp_input = CompensationInput(
        country_id=india.id,
        target_currency_id=inr.id,
        regime="new",
        as_of_date=date.today(),
    )
    comp_input.components.append(_component(ComponentType.BASE, "1500000.00", inr))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.gross_amount == Decimal("1500000.00")
    assert calculation.total_tax_amount == Decimal("93750.00")
    assert calculation.net_amount == Decimal("1406250.00")


def test_spain_combines_income_tax_and_social_security(db_session: Session) -> None:
    """EUR50,000 base, Spain: state IRPF scale (no standard_deduction
    seeded, so income_tax base = full gross) plus social_security.

    Hand math (IRPF, cross-checked against the Phase 2 research's own
    cumulative "base tax" column at each threshold):
      [0,12450)*.095=1182.75; [12450,20200)*.12=930.00 (running: 2112.75);
      [20200,35200)*.15=2250.00 (running: 4362.75);
      [35200,60000)->(50000-35200)=14800*.185=2738.00 (running: 7100.75)
      income_tax total = 7100.75
      social_security: 50000 * .0485 = 2425.00 (below the 61214.40 cap)
      total_tax = 7100.75 + 2425.00 = 9525.75
      net = 50000 - 9525.75 = 40474.25
    """
    spain = _country(db_session, "ES")
    eur = _currency(db_session, "EUR")

    comp_input = CompensationInput(
        country_id=spain.id, target_currency_id=eur.id, as_of_date=date.today()
    )
    comp_input.components.append(_component(ComponentType.BASE, "50000.00", eur))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.total_tax_amount == Decimal("9525.75")
    assert calculation.net_amount == Decimal("40474.25")
    assert calculation.breakdown["tax"]["standard_deduction"] is None


def test_no_matching_tax_rule_set_leaves_tax_fields_null(db_session: Session) -> None:
    """A filing_status that matches no seeded rule set: gross/total are
    still computed (currency conversion doesn't depend on tax), but
    tax_rule_set_id/total_tax_amount/net_amount stay None rather than
    guessing or erroring.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")

    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="married_filing_jointly",
        as_of_date=date.today(),
    )
    comp_input.components.append(_component(ComponentType.BASE, "100000.00", usd))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.gross_amount == Decimal("100000.00")
    assert calculation.tax_rule_set_id is None
    assert calculation.total_tax_amount is None
    assert calculation.net_amount is None
    assert calculation.breakdown["tax"] is None


def test_multi_currency_components_use_a_fixtured_exchange_rate(db_session: Session) -> None:
    """USD base + an INR bonus, target USD: the INR component must be
    converted using the fixtured USD->INR rate (83.00000000).
    500000 / 83 = 6024.096385... -> 6024.10.

    Exchange rates aren't part of the global seed (Phase 6) - this test
    inserts its own row, dated to match the CompensationInput's own
    as_of_date, so get_closest_exchange_rate's nearest-date lookup
    resolves it unambiguously.
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")
    inr = _currency(db_session, "INR")
    today = date.today()
    db_session.add(
        ExchangeRate(
            base_currency_id=usd.id,
            quote_currency_id=inr.id,
            rate=Decimal("83.00000000"),
            as_of_date=today,
            source="test-fixture",
        )
    )
    db_session.flush()

    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="single",
        as_of_date=today,
    )
    comp_input.components.append(_component(ComponentType.BASE, "100000.00", usd))
    comp_input.components.append(_component(ComponentType.BONUS, "500000.00", inr))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)

    assert calculation.gross_amount == Decimal("106024.10")
    assert "USD->INR" in calculation.breakdown["rates_used"]


def test_missing_exchange_rate_propagates_not_swallowed(db_session: Session) -> None:
    """India-sourced income normalized to EUR: no INR-EUR rate (direct or
    inverse) exists, and the engine must not silently guess via a third
    currency - the error should propagate to the caller.
    """
    india = _country(db_session, "IN")
    inr = _currency(db_session, "INR")
    eur = _currency(db_session, "EUR")

    comp_input = CompensationInput(
        country_id=india.id, target_currency_id=eur.id, as_of_date=date.today()
    )
    comp_input.components.append(_component(ComponentType.BASE, "100000.00", inr))
    db_session.add(comp_input)
    db_session.flush()

    with pytest.raises(MissingExchangeRateError):
        run_calculation(db_session, comp_input)


def test_calculation_persists_and_is_queryable_after_commit(db_session: Session) -> None:
    """run_calculation() only stages (session.add) - proves it actually
    persists once the caller commits, and that a fresh query returns the
    same values (not just an in-memory object that looks right).
    """
    us = _country(db_session, "US")
    usd = _currency(db_session, "USD")

    comp_input = CompensationInput(
        country_id=us.id,
        target_currency_id=usd.id,
        filing_status="single",
        as_of_date=date.today(),
    )
    comp_input.components.append(_component(ComponentType.BASE, "80000.00", usd))
    db_session.add(comp_input)
    db_session.flush()

    calculation = run_calculation(db_session, comp_input)
    db_session.commit()
    calculation_id = calculation.id
    db_session.expire_all()

    reloaded = db_session.get(Calculation, calculation_id)
    assert reloaded is not None
    assert reloaded.gross_amount == Decimal("80000.00")
    assert reloaded.engine_version == ENGINE_VERSION

    # This is the one test in the suite that must commit (to prove commit
    # actually persists), so unlike every other test here it isn't rolled
    # back automatically by db_session's implicit close-on-exit rollback.
    # Clean up explicitly rather than accumulating a row set in
    # compintel_test on every local test run.
    db_session.delete(reloaded)
    comp_input_reloaded = db_session.get(CompensationInput, comp_input.id)
    if comp_input_reloaded is not None:
        db_session.delete(comp_input_reloaded)
    db_session.commit()
