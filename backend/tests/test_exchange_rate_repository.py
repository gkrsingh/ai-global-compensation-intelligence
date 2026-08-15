"""Tests for the 'closest available' exchange rate fallback (deferred from
step 2, implemented in step 5's repositories.py).

Each test inserts its own exchange rate row(s) explicitly rather than
relying on any globally seeded rate - as of Phase 6, exchange rates are
no longer part of the static reference-data seed at all (they come from
fetch_exchange_rates.py, a real provider, not a committed fixture), so a
test that needs specific rate data sets it up itself, the same way the
"closer"/"newer_but_farther" rows already did before this change.
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


def _seed_rate(
    db_session: Session,
    base_code: str,
    quote_code: str,
    rate: str,
    as_of: date,
    source: str = "test-fixture",
) -> ExchangeRate:
    base = _currency(db_session, base_code)
    quote = _currency(db_session, quote_code)
    row = ExchangeRate(
        base_currency_id=base.id,
        quote_currency_id=quote.id,
        rate=Decimal(rate),
        as_of_date=as_of,
        source=source,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_picks_the_closer_of_two_candidates_not_just_the_newest(db_session: Session) -> None:
    """Two USD->INR candidates at different dates; the query date is
    closer to the second (later-added) one - proves genuine closest-by-
    date selection, not "always pick the most recently added".
    """
    _seed_rate(db_session, "USD", "INR", "83.00000000", date(2026, 1, 1))
    _seed_rate(db_session, "USD", "INR", "90.00000000", date(2026, 6, 15))

    result = get_closest_exchange_rate(db_session, "USD", "INR", date(2026, 6, 20))

    assert result is not None
    assert result.rate == Decimal("90.00000000")


def test_picks_the_older_seeded_rate_when_it_is_actually_closer(db_session: Session) -> None:
    """The inverse of the test above: a NEWER candidate exists, but the
    query date is closer to the older one. Proves this isn't secretly
    "always pick newest" - it has to genuinely compare distances both
    ways.
    """
    _seed_rate(db_session, "USD", "INR", "83.00000000", date(2026, 1, 1))
    _seed_rate(db_session, "USD", "INR", "95.00000000", date(2027, 1, 1))

    result = get_closest_exchange_rate(db_session, "USD", "INR", date(2026, 1, 5))

    assert result is not None
    assert result.rate == Decimal("83.00000000")


def test_find_rate_either_direction_finds_the_inverse_pair(db_session: Session) -> None:
    """Only USD->INR (base=USD) is fixtured. Asking for INR,USD (reversed
    argument order) should still resolve via the inverse search, returning
    the direction it was actually found in.
    """
    _seed_rate(db_session, "USD", "INR", "83.00000000", date(2026, 1, 1))

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
    currencies in the SAME order they were actually fixtured (base=USD
    first) should resolve via the direct match, not fall through to the
    inverse search. Every other call site in the suite (including the
    engine's own multi-currency test) happens to call this with currency_a
    as the component currency and currency_b as the target, which for a
    USD-anchored rate always hits the inverse path - so the direct match
    had never actually been exercised until this test.
    """
    _seed_rate(db_session, "USD", "INR", "83.00000000", date(2026, 1, 1))

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
