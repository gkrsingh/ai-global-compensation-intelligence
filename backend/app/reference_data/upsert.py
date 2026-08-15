"""Generic upsert-by-natural-key helper, shared by every idempotent
reference-data writer (seed.py, fetch_exchange_rates.py). Extracted here
once a second real caller needed the exact same logic, rather than
duplicated verbatim.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def upsert(
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
