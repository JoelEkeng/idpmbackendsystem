from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import Base, engine  # your async engine
from app.models import *  # import all your models here

# this is the Alembic Config object
config = context.config

def include_object(object, name, type_, reflected, compare_to):
    # Ignore BetterAuth tables
    ignored_tables = {"user", "session", "account", "verification"}
    if type_ == "table" and name in ignored_tables:
        return False
    return True

fileConfig(config.config_file_name)
target_metadata = Base.metadata

# Async run
def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = engine

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())