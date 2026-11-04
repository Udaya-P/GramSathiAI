from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401: registers all tables

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=get_settings().database_url.get_secret_value(),
                      target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Test setup may supply a connection bound to its isolated random schema.
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(get_settings().database_url.get_secret_value(), poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
