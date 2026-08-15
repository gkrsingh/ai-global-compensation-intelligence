from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reference_data.exchange_rate_provider import ExchangeRateProvider, Rate
from app.reference_data.fetch_exchange_rates import (
    _compute_cross_rate,
    _get_currency,
    fetch_and_persist,
)
from app.reference_data.models import Currency, ExchangeRate


class _FakeProvider(ExchangeRateProvider):
    """A canned provider, not a mock of HTTP - the adapter's real HTTP
    behavior is already covered by test_exchange_rate_provider.py. This
    tests the ingestion script's own logic: fetching, deriving the cross
    rate, and persisting - independent of how a rate was obtained.
    """

    def __init__(self, rates: dict[tuple[str, str], Rate]) -> None:
        self._rates = rates

    def get_rate(self, base: str, quote: str, as_of: date) -> Rate:
        return self._rates[(base, quote)]


def _make_rate(base: str, quote: str, rate: str, as_of: date) -> Rate:
    return Rate(
        base=base,
        quote=quote,
        rate=Decimal(rate),
        as_of_date=as_of,
        source="Frankfurter API (ECB reference rate)",
    )


def _delete_rates_for_date(db_session: Session, as_of: date) -> None:
    rows = db_session.scalars(select(ExchangeRate).where(ExchangeRate.as_of_date == as_of)).all()
    for row in rows:
        db_session.delete(row)
    db_session.commit()


def test_get_currency_raises_a_clear_error_for_an_unknown_code(db_session: Session) -> None:
    with pytest.raises(RuntimeError, match="ZZZ"):
        _get_currency(db_session, "ZZZ")


def test_compute_cross_rate_derives_inr_to_eur_from_two_usd_anchored_rates() -> None:
    as_of = date(2026, 8, 14)
    inr_rate = _make_rate("USD", "INR", "95.43", as_of)
    eur_rate = _make_rate("USD", "EUR", "0.86453", as_of)

    cross = _compute_cross_rate(inr_rate, eur_rate)

    assert cross.base == "INR"
    assert cross.quote == "EUR"
    assert cross.as_of_date == as_of
    # 1 USD = 95.43 INR = 0.86453 EUR, so 1 INR = 0.86453 / 95.43 EUR.
    expected = (Decimal("0.86453") / Decimal("95.43")).quantize(Decimal("0.00000001"))
    assert cross.rate == expected
    assert "derived via USD" in cross.source
    assert "Frankfurter" in cross.source


def test_compute_cross_rate_raises_if_the_two_fetched_rates_are_for_different_dates() -> None:
    inr_rate = _make_rate("USD", "INR", "95.43", date(2026, 8, 14))
    eur_rate = _make_rate("USD", "EUR", "0.86453", date(2026, 8, 13))

    with pytest.raises(RuntimeError, match="different dates"):
        _compute_cross_rate(inr_rate, eur_rate)


def test_fetch_and_persist_writes_two_fetched_rows_and_one_derived_row(
    db_session: Session,
) -> None:
    as_of = date(2026, 8, 14)
    provider = _FakeProvider(
        {
            ("USD", "INR"): _make_rate("USD", "INR", "95.43", as_of),
            ("USD", "EUR"): _make_rate("USD", "EUR", "0.86453", as_of),
        }
    )

    try:
        rates = fetch_and_persist(db_session, provider, as_of)

        assert len(rates) == 3
        pairs = {(r.base, r.quote) for r in rates}
        assert pairs == {("USD", "INR"), ("USD", "EUR"), ("INR", "EUR")}

        inr = db_session.scalar(select(Currency).where(Currency.code == "INR"))
        eur = db_session.scalar(select(Currency).where(Currency.code == "EUR"))
        assert inr is not None
        assert eur is not None
        persisted_cross = db_session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency_id == inr.id,
                ExchangeRate.quote_currency_id == eur.id,
                ExchangeRate.as_of_date == as_of,
            )
        )
        assert persisted_cross is not None
        assert persisted_cross.source.startswith("derived via USD")
    finally:
        _delete_rates_for_date(db_session, as_of)


def test_fetch_and_persist_is_idempotent_for_the_same_date(db_session: Session) -> None:
    as_of = date(2026, 8, 14)
    first_run = _FakeProvider(
        {
            ("USD", "INR"): _make_rate("USD", "INR", "95.43", as_of),
            ("USD", "EUR"): _make_rate("USD", "EUR", "0.86453", as_of),
        }
    )
    second_run = _FakeProvider(
        {
            ("USD", "INR"): _make_rate("USD", "INR", "96.00", as_of),
            ("USD", "EUR"): _make_rate("USD", "EUR", "0.87000", as_of),
        }
    )

    try:
        fetch_and_persist(db_session, first_run, as_of)
        fetch_and_persist(db_session, second_run, as_of)

        rows = db_session.scalars(
            select(ExchangeRate).where(ExchangeRate.as_of_date == as_of)
        ).all()
        # Still exactly 3 rows (2 fetched + 1 derived) - re-running for the
        # same date updates in place, never duplicates.
        assert len(rows) == 3

        usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
        inr = db_session.scalar(select(Currency).where(Currency.code == "INR"))
        assert usd is not None
        assert inr is not None
        updated = db_session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency_id == usd.id,
                ExchangeRate.quote_currency_id == inr.id,
                ExchangeRate.as_of_date == as_of,
            )
        )
        assert updated is not None
        assert updated.rate == Decimal("96.00000000")
    finally:
        _delete_rates_for_date(db_session, as_of)


def test_fetch_and_persist_on_a_new_date_adds_rows_without_touching_the_old_ones(
    db_session: Session,
) -> None:
    first_date = date(2026, 8, 13)
    second_date = date(2026, 8, 14)
    first_run = _FakeProvider(
        {
            ("USD", "INR"): _make_rate("USD", "INR", "95.00", first_date),
            ("USD", "EUR"): _make_rate("USD", "EUR", "0.86000", first_date),
        }
    )
    second_run = _FakeProvider(
        {
            ("USD", "INR"): _make_rate("USD", "INR", "95.43", second_date),
            ("USD", "EUR"): _make_rate("USD", "EUR", "0.86453", second_date),
        }
    )

    try:
        fetch_and_persist(db_session, first_run, first_date)
        fetch_and_persist(db_session, second_run, second_date)

        usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
        inr = db_session.scalar(select(Currency).where(Currency.code == "INR"))
        assert usd is not None
        assert inr is not None

        first_row = db_session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency_id == usd.id,
                ExchangeRate.quote_currency_id == inr.id,
                ExchangeRate.as_of_date == first_date,
            )
        )
        second_row = db_session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency_id == usd.id,
                ExchangeRate.quote_currency_id == inr.id,
                ExchangeRate.as_of_date == second_date,
            )
        )
        assert first_row is not None
        assert first_row.rate == Decimal("95.00000000")
        assert second_row is not None
        assert second_row.rate == Decimal("95.43000000")
    finally:
        _delete_rates_for_date(db_session, first_date)
        _delete_rates_for_date(db_session, second_date)
