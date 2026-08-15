from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.compensation import models as compensation_models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.reference_data import models as reference_data_models  # noqa: F401

# The two "models as ..._models" imports above exist purely so every
# domain's tables register with Base's metadata before autogenerate runs.
# db/base.py deliberately does not import these itself: compensation
# depends on reference_data, which is what triggers db.base's own import
# in the first place - having db.base also import compensation would be a
# real circular import, not just a reorder-able one. This standalone
# script has no such constraint, so it's the right place for it.

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL comes from the app's own Settings (env vars / .env), not from
# alembic.ini, so the same connection info and fail-fast-if-missing behavior
# apply here as everywhere else in the app, and alembic.ini stays secret-free.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
