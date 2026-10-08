from logging.config import fileConfig
from typing import Literal

from alembic.autogenerate.api import AutogenContext
from sqlalchemy import Connection

from alembic import context
from app.core.config import get_settings
from app.core.database import create_database_engine
from app.models import Base
from app.models.base import UTCDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def render_item(
    item_type: str, item: object, autogen_context: AutogenContext
) -> str | Literal[False]:
    if item_type == "type" and isinstance(item, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return "mysql.TIMESTAMP(fsp=6)"
    return False


def run_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=get_settings().database_url.get_secret_value(),
            target_metadata=Base.metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    supplied_connection = config.attributes.get("connection")
    if isinstance(supplied_connection, Connection):
        run_with_connection(supplied_connection)
        return

    engine = create_database_engine(get_settings().database_url.get_secret_value())
    try:
        with engine.connect() as connection:
            run_with_connection(connection)
    finally:
        engine.dispose()


run_migrations()
