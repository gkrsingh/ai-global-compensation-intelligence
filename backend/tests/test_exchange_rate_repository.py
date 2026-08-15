"""Tests for the 'closest available' exchange rate fallback (deferred from
step 2, implemented in step 5's repositories.py). Never exercised with
more than one candidate rate until now - Phase 2 seeded exactly one rate
per currency pair, so this policy has been sitting untested since it was
written.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compensation.repositories import find_rate_either_direction, get_closest_exchange_rate
from app.reference_data.models import Currency, ExchangeRate


def _currency(db_session: Session, code: str) -> Currency:
    currency = db_session.scalar(select(Currency).where(Currency.code == code))
    assert currency is not None
    return currency


def test_picks_the_closer_of_two_candidates_not_just_the_newest(db_session: Session) -> None:
    """Phase 2 seeded USD->INR at 2026-01-01 (rate 83). Add a second,
    closer to the query date, and confirm that one wins - proves genuine
    closest-by-date selection, not "always pick the most recently added".
    """
    usd = _currency(db_session, "USD")
    inr = _currency(db_session, "INR")
    closer = ExchangeRate(
        base_currency_id=usd.id,
        quote_currency_id=inr.id,
        rate=Decimal("90.00000000"),
        as_of_date=date(2026, 6, 15),
        source="test-closer",
    )
    db_session.add(closer)
    db_session.flush()

    result = get_closest_exchange_rate(db_session, "USD", "INR", date(2026, 6, 20))

    assert result is not None
    assert result.rate == Decimal("90.00000000")


def test_picks_the_older_seeded_rate_when_it_is_actually_closer(db_session: Session) -> None:
    """The inverse of the test above: a NEWER candidate exists, but the
    query date is closer to the original seeded (older) rate. Proves this
    isn't secretly "always pick newest" - it has to genuinely compare
    distances both ways.
    """
    usd = _currency(db_session, "USD")
    inr = _currency(db_session, "INR")
    newer_but_farther = ExchangeRate(
        base_currency_id=usd.id,
        quote_currency_id=inr.id,
        rate=Decimal("95.00000000"),
        as_of_date=date(2027, 1, 1),
        source="test-farther",
    )
    db_session.add(newer_but_farther)
    db_session.flush()

    result = get_closest_exchange_rate(db_session, "USD", "INR", date(2026, 1, 5))

    assert result is not None
    assert result.rate == Decimal("83.00000000")


def test_find_rate_either_direction_finds_the_inverse_pair(db_session: Session) -> None:
    """Only USD->INR (base=USD) is seeded. Asking for INR,USD (reversed
    argument order) should still resolve via the inverse search, returning
    the direction it was actually found in.
    """
    result = find_rate_either_direction(db_session, "INR", "USD", date(2026, 1, 1))

    assert result is not None
    base, quote, rate = result
    assert (base, quote) == ("USD", "INR")
    assert rate == Decimal("83.00000000")


def test_find_rate_either_direction_returns_none_when_truly_absent(db_session: Session) -> None:
    result = find_rate_either_direction(db_session, "INR", "EUR", date(2026, 1, 1))
    assert result is None


def test_find_rate_either_direction_finds_the_direct_pair(db_session: Session) -> None:
    """The counterpart to the inverse-pair test above: calling with the
    currencies in the SAME order they were actually seeded (base=USD
    first) should resolve via the direct match, not fall through to the
    inverse search. Every other call site in the suite (including the
    engine's own multi-currency test) happens to call this with currency_a
    as the component currency and currency_b as the target, which for the
    seeded USD-anchored rates always hits the inverse path - so the direct
    match had never actually been exercised until this test.
    """
    result = find_rate_either_direction(db_session, "USD", "INR", date(2026, 1, 1))

    assert result is not None
    base, quote, rate = result
    assert (base, quote) == ("USD", "INR")
    assert rate == Decimal("83.00000000")


def test_get_closest_exchange_rate_returns_none_for_unknown_currency_code(
    db_session: Session,
) -> None:
    result = get_closest_exchange_rate(db_session, "ZZZ", "USD", date(2026, 1, 1))
    assert result is None
