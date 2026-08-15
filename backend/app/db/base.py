from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base.

    Deliberately has NO domain model imports here. Domain modules (compensation,
    reference_data) import this module to get Base — if this module also
    imported domain modules for metadata-registration purposes, and one domain
    (compensation) depends on another (reference_data) which is what triggers
    this module's own import, that's a real circular import, not just a
    reorder-able one. Alembic's env.py is the right place for "make sure
    every model is registered" — it's a standalone script nothing else
    imports, so it can pull in every domain explicitly without any cycle risk.
    """
