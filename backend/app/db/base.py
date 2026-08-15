from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base.

    Alembic's env.py points target_metadata at this. Domain model modules
    are imported below purely for their side effect of registering with
    Base's metadata — Alembic's autogenerate can't see a model that was
    never imported anywhere in this chain.
    """


from app.reference_data import models as reference_data_models  # noqa: E402,F401
