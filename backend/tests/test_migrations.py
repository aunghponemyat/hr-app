from sqlalchemy import Engine, inspect, text

from alembic import command
from app.models import Base
from tests.database import migration_config


def test_initial_migration_round_trip_and_matches_models(db_engine: Engine) -> None:
    """DDL only runs through Alembic, and only on the guarded disposable test database."""
    with db_engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        command.check(config)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0002"
        )


def test_mysql_table_options_and_unsigned_identifiers(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME <> 'alembic_version'"
            )
        ).all()
        assert len(rows) == len(Base.metadata.tables)
        assert all(
            row.ENGINE == "InnoDB" and row.TABLE_COLLATION.startswith("utf8mb4") for row in rows
        )
        inspector = inspect(connection)
        for table_name in Base.metadata.tables:
            for column in inspector.get_columns(table_name):
                if column["name"] == "id" or column["name"].endswith("_id"):
                    if column["name"] == "employee_id" and table_name == "employees":
                        continue
                    assert getattr(column["type"], "unsigned", False), (table_name, column["name"])
            for foreign_key in inspector.get_foreign_keys(table_name):
                if table_name == "role_permissions":
                    assert foreign_key["options"]["ondelete"] == "CASCADE"


def test_required_indexes_and_primary_keys(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        inspector = inspect(connection)
        attendance_indexes = inspector.get_indexes("attendance")
        assert any(
            index["unique"] and index["column_names"] == ["employee_id", "attendance_date"]
            for index in attendance_indexes
        )
        assert any(index["column_names"] == ["attendance_date"] for index in attendance_indexes)
        leave_columns = {
            tuple(index["column_names"]) for index in inspector.get_indexes("leave_requests")
        }
        assert {
            ("employee_id", "start_date"),
            ("reporting_manager_id", "status"),
            ("status",),
        } <= leave_columns
        for table, columns in (
            ("role_permissions", ["role_id", "permission_id"]),
            ("team_members", ["team_id", "employee_id", "joined_at"]),
            ("team_managers", ["team_id", "employee_id", "assigned_at"]),
            ("team_work_locations", ["team_id", "work_location_id"]),
        ):
            assert inspector.get_pk_constraint(table)["constrained_columns"] == columns
