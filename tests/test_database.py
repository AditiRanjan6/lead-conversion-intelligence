import sqlite3

import pytest

from app.database import get_connection, initialize_database


def test_initialization_creates_registry_settings_and_leads_tables(tmp_path):
    database_path = tmp_path / "app.sqlite3"

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?",
                ("table",),
            )
        }

    assert {"datasets", "application_settings", "leads"} <= tables


def test_initialization_creates_dataset_scoped_lead_indexes(tmp_path):
    database_path = tmp_path / "app.sqlite3"

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(leads)")
        }

    assert {
        "idx_leads_dataset_created",
        "idx_leads_dataset_stage",
        "idx_leads_dataset_source",
        "idx_leads_dataset_last_activity",
        "idx_leads_dataset_follow_up",
        "idx_leads_dataset_converted",
    } <= indexes


def test_repeated_initialization_is_idempotent(tmp_path):
    database_path = tmp_path / "app.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        datasets = connection.execute(
            "SELECT COUNT(*) AS count FROM datasets"
        ).fetchone()["count"]

    assert datasets == 0


def test_connection_configuration_and_cleanup(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        assert isinstance(connection.execute("SELECT 1 AS value").fetchone(), sqlite3.Row)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        closed_connection = connection

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        closed_connection.execute("SELECT 1")


def test_connection_rolls_back_on_exception(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    initialize_database(database_path)

    with pytest.raises(RuntimeError, match="force rollback"):
        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO datasets (dataset_id, name, dataset_type)
                VALUES (?, ?, ?)
                """,
                ("rolled-back", "Temporary", "synthetic"),
            )
            raise RuntimeError("force rollback")

    with get_connection(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM datasets WHERE dataset_id = ?",
            ("rolled-back",),
        ).fetchone()["count"]

    assert count == 0
