from pathlib import Path

from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def validate_test_database_url(test_url: str, development_url: str) -> None:
    test = make_url(test_url)
    development = make_url(development_url)
    if (
        not test.database
        or not test.database.endswith("_test")
        or test.database == development.database
    ):
        raise ValueError("TEST_DATABASE_URL must target a separate database ending in '_test'.")


def migration_config(connection: Connection) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["connection"] = connection
    return config
