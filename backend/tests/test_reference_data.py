from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reference_data.models import Country, Currency, TaxComponent
from app.reference_data.queries import AmbiguousTaxRuleSetError, get_effective_tax_rule_set


def test_currencies_and_countries_seeded(db_session: Session) -> None:
    currency_codes = set(db_session.scalars(select(Currency.code)).all())
    assert {"INR", "USD", "EUR"} <= currency_codes

    country_codes = set(db_session.scalars(select(Country.code)).all())
    assert {"IN", "US", "ES"} <= country_codes


def test_india_new_regime_brackets_as_of_today(db_session: Session) -> None:
    rule_set = get_effective_tax_rule_set(db_session, "IN", date.today(), regime="new")

    assert rule_set is not None
    assert rule_set.standard_deduction == 75000

    brackets = rule_set.tax_brackets
    income_tax_brackets = [b for b in brackets if b.component == TaxComponent.INCOME_TAX]
    assert len(income_tax_brackets) == 7
    assert income_tax_brackets[0].lower_bound == 0
    assert income_tax_brackets[0].rate == 0
    assert income_tax_brackets[-1].upper_bound is None
    assert income_tax_brackets[-1].rate == Decimal("0.30000")


def test_india_old_regime_brackets_as_of_today(db_session: Session) -> None:
    rule_set = get_effective_tax_rule_set(db_session, "IN", date.today(), regime="old")

    assert rule_set is not None
    assert rule_set.standard_deduction == 50000
    assert len(rule_set.tax_brackets) == 4


def test_us_single_filer_brackets_as_of_today(db_session: Session) -> None:
    rule_set = get_effective_tax_rule_set(
        db_session, "US", date.today(), filing_status="single"
    )

    assert rule_set is not None
    assert rule_set.standard_deduction == 16100

    by_component = {
        component: [b for b in rule_set.tax_brackets if b.component == component]
        for component in TaxComponent
    }
    assert len(by_component[TaxComponent.INCOME_TAX]) == 7
    assert len(by_component[TaxComponent.SOCIAL_SECURITY]) == 1
    assert by_component[TaxComponent.SOCIAL_SECURITY][0].upper_bound == 184500
    assert len(by_component[TaxComponent.MEDICARE]) == 1
    assert by_component[TaxComponent.MEDICARE][0].upper_bound is None
    assert len(by_component[TaxComponent.MEDICARE_ADDITIONAL_SURTAX]) == 1


def test_spain_brackets_as_of_today(db_session: Session) -> None:
    rule_set = get_effective_tax_rule_set(db_session, "ES", date.today())

    assert rule_set is not None
    assert rule_set.standard_deduction is None

    components = {b.component for b in rule_set.tax_brackets}
    assert components == {TaxComponent.INCOME_TAX, TaxComponent.SOCIAL_SECURITY}


def test_returns_none_for_unknown_regime(db_session: Session) -> None:
    rule_set = get_effective_tax_rule_set(db_session, "IN", date.today(), regime="nonexistent")
    assert rule_set is None


def test_returns_none_before_effective_date(db_session: Session) -> None:
    """Proves the date-range filter actually filters, not just present for show."""
    rule_set = get_effective_tax_rule_set(
        db_session, "US", date(2020, 1, 1), filing_status="single"
    )
    assert rule_set is None


def test_raises_ambiguous_error_for_india_without_regime(db_session: Session) -> None:
    """India has both an old- and a new-regime TaxRuleSet effective today,
    so asking for "IN as of today" without a regime is genuinely
    ambiguous, not a bug in the seed data. Found via real UI testing in
    Phase 4 - the Calculator form doesn't collect regime, and this path
    had never been exercised without one before.
    """
    with pytest.raises(AmbiguousTaxRuleSetError) as exc_info:
        get_effective_tax_rule_set(db_session, "IN", date.today())

    assert "IN" in str(exc_info.value)
