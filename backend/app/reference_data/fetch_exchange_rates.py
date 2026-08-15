"""Fetches real exchange rates from the configured ExchangeRateProvider
and persists them, idempotently, as ExchangeRate rows.

Run via `python -m app.reference_data.fetch_exchange_rates`.

Fetches direct USD-anchored rates for every other seeded currency
(USD->INR, USD->EUR), then computes and persists the derived cross rate
for the remaining pair (INR->EUR) that isn't reachable from either
fetched row without triangulation. Phase 3's convert_amount() does a
direct-or-inverse lookup only, by design - never triangulation - so this
script is where any triangulation happens: once, explicitly, logged and
auditable via the source field, not silently and repeatedly recomputed
at conversion time (which would also silently compound floating-point
error on every use).

Idempotent like seed.py: each currency pair is upserted by its natural
key (base, quote, as_of_date), so re-running for the same date updates
those rows in place rather than duplicating them. Running again on a
LATER date inserts new dated rows instead - each fetch is a new
historical data point, not an overwrite of history.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.reference_data.exchange_rate_provider import (
    ExchangeRateProvider,
    FrankfurterProvider,
    Rate,
)
from app.reference_data.models import Currency, ExchangeRate
from app.reference_data.upsert import upsert

# USD-anchored pairs fetched directly. Every other pair among the
# seeded currencies is derived from these at ingestion time (see
# _compute_cross_rates) rather than fetched separately - fewer API
# calls, and every derived rate stays traceable to exactly which two
# fetched rates produced it.
ANCHOR_CURRENCY = "USD"
QUOTE_CURRENCIES = ["INR", "EUR"]

_RATE_DECIMAL_PLACES = 8


def _quantize_rate(value: Decimal) -> Decimal:
    quantum = Decimal(1).scaleb(-_RATE_DECIMAL_PLACES)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _get_currency(session: Session, code: str) -> Currency:
    currency = session.scalar(select(Currency).where(Currency.code == code))
    if currency is None:
        raise RuntimeError(f"Currency {code!r} not found - run seed.py before this script.")
    return currency


def _compute_cross_rate(inr_rate: Rate, eur_rate: Rate) -> Rate:
    """Derives INR->EUR from the two USD-anchored fetched rates.

    1 USD = inr_rate.rate INR, and 1 USD = eur_rate.rate EUR, so
    1 INR = (eur_rate.rate / inr_rate.rate) EUR.
    """
    if inr_rate.as_of_date != eur_rate.as_of_date:
        raise RuntimeError(
            f"Cannot derive INR->EUR: fetched rates are for different dates "
            f"({inr_rate.as_of_date} vs {eur_rate.as_of_date})"
        )

    return Rate(
        base="INR",
        quote="EUR",
        rate=_quantize_rate(eur_rate.rate / inr_rate.rate),
        as_of_date=inr_rate.as_of_date,
        source=f"derived via USD, provider: {eur_rate.source}",
    )


def _persist_rate(session: Session, currencies: dict[str, Currency], rate: Rate) -> None:
    base = currencies[rate.base]
    quote = currencies[rate.quote]
    natural_key = {
        "base_currency_id": base.id,
        "quote_currency_id": quote.id,
        "as_of_date": rate.as_of_date,
    }
    values = {"rate": _quantize_rate(rate.rate), "source": rate.source}
    upsert(session, ExchangeRate, natural_key, values)


def fetch_and_persist(
    session: Session, provider: ExchangeRateProvider, as_of: date
) -> list[Rate]:
    """Stages (flushes) but does not commit - committing is the caller's
    job, consistent with the outermost caller controlling the
    transaction (same design as the compensation engine's
    run_calculation). If a later fetch in this batch fails, the whole
    run rolls back on session close rather than persisting a partial,
    internally-inconsistent set of rates.
    """
    currencies = {
        code: _get_currency(session, code) for code in [ANCHOR_CURRENCY, *QUOTE_CURRENCIES]
    }

    fetched = {
        quote_code: provider.get_rate(ANCHOR_CURRENCY, quote_code, as_of)
        for quote_code in QUOTE_CURRENCIES
    }
    for rate in fetched.values():
        _persist_rate(session, currencies, rate)

    derived = [_compute_cross_rate(fetched["INR"], fetched["EUR"])]
    for rate in derived:
        _persist_rate(session, currencies, rate)

    session.flush()
    return [*fetched.values(), *derived]


def main() -> None:
    with FrankfurterProvider() as provider, SessionLocal() as session:
        rates = fetch_and_persist(session, provider, date.today())
        session.commit()
        for rate in rates:
            print(
                f"{rate.base}->{rate.quote}: {rate.rate} (as of {rate.as_of_date}) [{rate.source}]"
            )


if __name__ == "__main__":
    main()
