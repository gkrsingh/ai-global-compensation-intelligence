"""Data loading for the calculation engine - the DB-touching counterpart
to the pure services/. Per the Phase 3 hard constraint, calculation logic
never queries the database itself; everything here loads data first, then
hands it to the pure functions in services/.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reference_data.models import Currency, ExchangeRate


def get_closest_exchange_rate(
    session: Session,
    base_currency_code: str,
    quote_currency_code: str,
    as_of: date,
) -> ExchangeRate | None:
    """The ExchangeRate for (base, quote) whose as_of_date is closest to
    `as_of` - literally closest by absolute day difference, not "most
    recent past only". With Phase 2's single seeded rate per pair this
    can't yet produce a visible difference, but it's the right policy for
    when a real rate-fetching integration adds daily rates later.
    """
    base = session.scalar(select(Currency).where(Currency.code == base_currency_code))
    quote = session.scalar(select(Currency).where(Currency.code == quote_currency_code))
    if base is None or quote is None:
        return None

    candidates = list(
        session.scalars(
            select(ExchangeRate).where(
                ExchangeRate.base_currency_id == base.id,
                ExchangeRate.quote_currency_id == quote.id,
            )
        )
    )
    if not candidates:
        return None

    return min(candidates, key=lambda r: abs((r.as_of_date - as_of).days))


def find_rate_either_direction(
    session: Session, currency_a: str, currency_b: str, as_of: date
) -> tuple[str, str, Decimal] | None:
    """A rate connecting currency_a and currency_b, in whichever direction
    is actually stored. ExchangeRate rows are directional (base/quote),
    but currency.convert_amount accepts either direction, so the caller
    doesn't need to know which way a given pair happened to be seeded.
    Returns (base_code, quote_code, rate) for whichever direction was
    found, or None if neither exists.
    """
    rate = get_closest_exchange_rate(session, currency_a, currency_b, as_of)
    if rate is not None:
        return currency_a, currency_b, rate.rate

    rate = get_closest_exchange_rate(session, currency_b, currency_a, as_of)
    if rate is not None:
        return currency_b, currency_a, rate.rate

    return None


def build_rates(
    session: Session, from_currencies: set[str], to_currency: str, as_of: date
) -> dict[tuple[str, str], Decimal]:
    """A rates dict (keyed the same way convert_amount expects) covering
    every currency in `from_currencies` that has a real path to
    `to_currency`. Currencies with no available rate are simply absent -
    callers find out via convert_amount's MissingExchangeRateError at the
    point they actually need that specific pair, not here.

    Originally private to the calculation engine (Phase 3-6); promoted
    here once Phase 7's comparison feature became a second real caller
    needing the identical "rates dict for a set of source currencies -> one
    target" logic - same extract-on-second-use discipline as upsert() in
    app/reference_data/upsert.py.
    """
    rates: dict[tuple[str, str], Decimal] = {}
    for currency_code in from_currencies:
        if currency_code == to_currency:
            continue
        found = find_rate_either_direction(session, currency_code, to_currency, as_of)
        if found is not None:
            base, quote, rate = found
            rates[(base, quote)] = rate
    return rates
