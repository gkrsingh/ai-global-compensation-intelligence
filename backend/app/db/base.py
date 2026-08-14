from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. No models yet — Phase 1A has no domain schema.

    Alembic's env.py points target_metadata at this so future models need
    only inherit from it to be picked up by autogenerate.
    """
