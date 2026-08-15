"""Idempotent reference/taxonomy data seeding.

Run via `python -m app.reference_data.seed`. Every entity is upserted by
its natural business key (not blindly inserted), so this is safe to re-run
after a data correction — never duplicates, updates in place if the seed
data changed since the last run.

Seeds currencies, countries, job families, experience levels, employment
types, and a couple of illustrative exchange rates — reference data that
needs no research/citation. TaxRuleSet/TaxBracket seeding (the real, cited
India/US/Spain tax figures) is added on top of this same mechanism
separately, since that data does need citation and is easy to get wrong.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.reference_data.models import (
    Country,
    Currency,
    EmploymentType,
    ExchangeRate,
    ExperienceLevel,
    JobFamily,
)


def _upsert(
    session: Session,
    model: type[Any],
    natural_key: dict[str, Any],
    values: dict[str, Any],
) -> Any:
    """Insert a row matching natural_key, or update it in place if present.

    NULL-safe: a None in natural_key is matched with IS NULL, not `= NULL`
    (which would never match anything in SQL).
    """
    stmt = select(model)
    for field, value in natural_key.items():
        column = getattr(model, field)
        stmt = stmt.where(column.is_(None) if value is None else column == value)
    existing = session.execute(stmt).scalar_one_or_none()

    if existing is None:
        obj = model(**natural_key, **values)
        session.add(obj)
        return obj

    for field, value in values.items():
        setattr(existing, field, value)
    return existing


_CURRENCIES: list[dict[str, Any]] = [
    {"code": "INR", "name": "Indian Rupee", "symbol": "₹", "decimal_places": 2},
    {"code": "USD", "name": "US Dollar", "symbol": "$", "decimal_places": 2},
    {"code": "EUR", "name": "Euro", "symbol": "€", "decimal_places": 2},
]

_COUNTRIES: list[dict[str, Any]] = [
    {"code": "IN", "name": "India", "default_currency_code": "INR"},
    {"code": "US", "name": "United States", "default_currency_code": "USD"},
    {"code": "ES", "name": "Spain", "default_currency_code": "EUR"},
]

_JOB_FAMILIES: list[str] = [
    "Software Engineering",
    "Product Management",
    "Data & Analytics",
    "Design",
    "Sales",
]

_EXPERIENCE_LEVELS: list[dict[str, Any]] = [
    {"name": "Junior", "rank": 1},
    {"name": "Mid", "rank": 2},
    {"name": "Senior", "rank": 3},
    {"name": "Staff", "rank": 4},
    {"name": "Principal", "rank": 5},
]

_EMPLOYMENT_TYPES: list[dict[str, str]] = [
    {"code": "FULL_TIME", "name": "Full-time"},
    {"code": "CONTRACT", "name": "Contract"},
    {"code": "PART_TIME", "name": "Part-time"},
]

# Illustrative only — proves the table shape works, not meant to be
# currently accurate. Real rate-fetching is a later integration (see the
# original architecture's External Integration Architecture section).
_EXCHANGE_RATES: list[dict[str, Any]] = [
    {
        "base_code": "USD",
        "quote_code": "INR",
        "rate": Decimal("83.00000000"),
        "as_of_date": date(2026, 1, 1),
        "source": "manual-seed-illustrative",
    },
    {
        "base_code": "USD",
        "quote_code": "EUR",
        "rate": Decimal("0.92000000"),
        "as_of_date": date(2026, 1, 1),
        "source": "manual-seed-illustrative",
    },
]


def seed_currencies(session: Session) -> dict[str, Currency]:
    result: dict[str, Currency] = {}
    for data in _CURRENCIES:
        code = data["code"]
        values = {k: v for k, v in data.items() if k != "code"}
        result[code] = _upsert(session, Currency, {"code": code}, values)
    session.flush()
    return result


def seed_countries(session: Session, currencies: dict[str, Currency]) -> dict[str, Country]:
    result: dict[str, Country] = {}
    for data in _COUNTRIES:
        code = data["code"]
        currency = currencies[data["default_currency_code"]]
        values = {"name": data["name"], "default_currency_id": currency.id}
        result[code] = _upsert(session, Country, {"code": code}, values)
    session.flush()
    return result


def seed_job_families(session: Session) -> None:
    for name in _JOB_FAMILIES:
        _upsert(session, JobFamily, {"name": name}, {})
    session.flush()


def seed_experience_levels(session: Session) -> None:
    for data in _EXPERIENCE_LEVELS:
        _upsert(session, ExperienceLevel, {"name": data["name"]}, {"rank": data["rank"]})
    session.flush()


def seed_employment_types(session: Session) -> None:
    for data in _EMPLOYMENT_TYPES:
        _upsert(session, EmploymentType, {"code": data["code"]}, {"name": data["name"]})
    session.flush()


def seed_exchange_rates(session: Session, currencies: dict[str, Currency]) -> None:
    for data in _EXCHANGE_RATES:
        base = currencies[data["base_code"]]
        quote = currencies[data["quote_code"]]
        natural_key = {
            "base_currency_id": base.id,
            "quote_currency_id": quote.id,
            "as_of_date": data["as_of_date"],
        }
        values = {"rate": data["rate"], "source": data["source"]}
        _upsert(session, ExchangeRate, natural_key, values)
    session.flush()


def seed_all(session: Session) -> None:
    currencies = seed_currencies(session)
    seed_countries(session, currencies)
    seed_job_families(session)
    seed_experience_levels(session)
    seed_employment_types(session)
    seed_exchange_rates(session, currencies)
    session.commit()


def main() -> None:
    with SessionLocal() as session:
        seed_all(session)


if __name__ == "__main__":
    main()
