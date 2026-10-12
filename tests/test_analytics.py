import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.database import get_connection, initialize_database
from app.main import app
from app.services.analytics import get_growth_overview
from app.services.datasets import register_dataset, select_active_dataset


@pytest.fixture
def analytics_db(tmp_path):
    db_path = tmp_path / "analytics_test.sqlite3"
    initialize_database(db_path)

    with get_connection(db_path) as connection:
        register_dataset(
            connection,
            dataset_id="analytics-test",
            name="Analytics Test",
            dataset_type="synthetic",
        )

        connection.executemany(
            """
            INSERT INTO leads (
                lead_id, dataset_id, name, acquisition_source, campaign,
                created_at, stage, status, is_qualified, assigned_owner,
                last_activity_at, next_follow_up_at, converted_at, deal_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "lead-1", "analytics-test", "Fictional Lead 1",
                    "paid_search", "Campaign A", "2026-10-01T10:00:00Z",
                    "closed_won", "converted", 1, "Owner A",
                    "2026-10-02T10:00:00Z", None,
                    "2026-10-02T10:00:00Z", 5000.0,
                ),
                (
                    "lead-2", "analytics-test", "Fictional Lead 2",
                    "organic_search", "Campaign B", "2026-10-03T10:00:00Z",
                   "qualified", "open", 1, "Owner B",
"2026-10-03T10:00:00Z", "2026-10-05T10:00:00Z",
None, None,
                ),
                (
                    "lead-3", "analytics-test", "Fictional Lead 3",
                    "referral", "Campaign C", "2026-10-04T10:00:00Z",
                    "closed_lost", "lost", 0, "Owner A",
                    "2026-10-04T10:00:00Z", None, None, None,
                ),
                (
                    "lead-4", "analytics-test", "Fictional Lead 4",
                    "paid_search", "Campaign D", "2026-10-05T10:00:00Z",
                    "new", "open", 0, "Owner B",
                    "2026-10-05T10:00:00Z", None, None, None,
                ),
            ],
        )

        register_dataset(
            connection,
            dataset_id="other-test",
            name="Other Test",
            dataset_type="synthetic",
        )

        connection.execute(
            """
            INSERT INTO leads (
                lead_id, dataset_id, name, acquisition_source, campaign,
                created_at, stage, status, is_qualified, assigned_owner,
                last_activity_at, next_follow_up_at, converted_at, deal_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "other-lead", "other-test", "Other Fictional Lead",
                "partner", "Other Campaign", "2026-10-06T10:00:00Z",
                "closed_won", "converted", 1, "Owner C",
                "2026-10-06T10:00:00Z", None,
                "2026-10-06T10:00:00Z", 9999.0,
            ),
        )

    return db_path


def test_growth_overview_calculates_metrics_for_one_dataset(analytics_db):
    with get_connection(analytics_db) as connection:
        result = get_growth_overview(connection, "analytics-test")

    assert result == {
        "total_leads": 4,
        "qualified_leads": 2,
        "converted_leads": 1,
        "lost_leads": 1,
        "conversion_rate": 25.0,
        "qualification_rate": 50.0,
        "converted_deal_value": 5000.0,
    }
    assert result["conversion_rate"] == 25.0
    assert result["qualification_rate"] == 50.0
    assert result["converted_deal_value"] == 5000.0


def test_growth_overview_does_not_include_other_datasets(analytics_db):
    with get_connection(analytics_db) as connection:
        result = get_growth_overview(connection, "analytics-test")

    assert result["total_leads"] == 4
    assert result["converted_leads"] == 1
    assert result["converted_deal_value"] == 5000.0


def test_growth_overview_returns_zero_metrics_for_empty_dataset(
    tmp_path,
):
    db_path = tmp_path / "empty_analytics.sqlite3"
    initialize_database(db_path)

    with get_connection(db_path) as connection:
        register_dataset(
            connection,
            dataset_id="empty-test",
            name="Empty Test",
            dataset_type="synthetic",
        )
        result = get_growth_overview(connection, "empty-test")

    assert result == {
        "total_leads": 0,
        "qualified_leads": 0,
        "converted_leads": 0,
        "lost_leads": 0,
        "conversion_rate": 0.0,
        "qualification_rate": 0.0,
        "converted_deal_value": 0.0,
    }


@pytest.mark.parametrize("dataset_id", ["missing-test", "bad id", ""])
def test_growth_overview_rejects_invalid_dataset_ids(
    analytics_db, dataset_id
):
    with get_connection(analytics_db) as connection:
        with pytest.raises(ValueError):
            get_growth_overview(connection, dataset_id)


def test_growth_overview_api_returns_metrics_without_mutating_data_or_selection(
    analytics_db,
    monkeypatch,
):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(analytics_db))

    with TestClient(app) as client:
        with get_connection(analytics_db) as connection:
            select_active_dataset(connection, "other-test")
            before = connection.execute(
                """
                SELECT lead_id, name, status, is_qualified, deal_value
                FROM leads
                WHERE dataset_id = ?
                ORDER BY lead_id
                """,
                ("analytics-test",),
            ).fetchall()

        response = client.get(
            "/api/analytics/growth",
            params={"dataset_id": "analytics-test"},
        )

        with get_connection(analytics_db) as connection:
            after = connection.execute(
                """
                SELECT lead_id, name, status, is_qualified, deal_value
                FROM leads
                WHERE dataset_id = ?
                ORDER BY lead_id
                """,
                ("analytics-test",),
            ).fetchall()
            active_dataset = connection.execute(
                "SELECT value FROM application_settings WHERE key = ?",
                ("active_dataset_id",),
            ).fetchone()["value"]

    assert response.status_code == 200
    assert response.json() == {
        "total_leads": 4,
        "qualified_leads": 2,
        "converted_leads": 1,
        "lost_leads": 1,
        "conversion_rate": 25.0,
        "qualification_rate": 50.0,
        "converted_deal_value": 5000.0,
    }
    assert set(response.json()) == {
        "total_leads",
        "qualified_leads",
        "converted_leads",
        "lost_leads",
        "conversion_rate",
        "qualification_rate",
        "converted_deal_value",
    }
    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    assert active_dataset == "other-test"


def test_growth_overview_api_requires_valid_registered_dataset_and_preserves_active(
    analytics_db,
    monkeypatch,
):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(analytics_db))

    with TestClient(app) as client:
        with get_connection(analytics_db) as connection:
            select_active_dataset(connection, "other-test")

        missing = client.get("/api/analytics/growth")
        blank = client.get("/api/analytics/growth", params={"dataset_id": ""})
        malformed = client.get(
            "/api/analytics/growth",
            params={"dataset_id": "bad id"},
        )
        unknown = client.get(
            "/api/analytics/growth",
            params={"dataset_id": "not-registered"},
        )

        with get_connection(analytics_db) as connection:
            active_dataset = connection.execute(
                "SELECT value FROM application_settings WHERE key = ?",
                ("active_dataset_id",),
            ).fetchone()["value"]

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert malformed.status_code == 422
    assert unknown.status_code == 404
    assert active_dataset == "other-test"


def test_growth_overview_api_returns_zeroes_for_empty_registered_dataset(
    analytics_db,
    monkeypatch,
):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(analytics_db))
    with get_connection(analytics_db) as connection:
        register_dataset(
            connection,
            dataset_id="empty-api",
            name="Empty API Dataset",
            dataset_type="real",
        )

    with TestClient(app) as client:
        response = client.get(
            "/api/analytics/growth",
            params={"dataset_id": "empty-api"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "total_leads": 0,
        "qualified_leads": 0,
        "converted_leads": 0,
        "lost_leads": 0,
        "conversion_rate": 0.0,
        "qualification_rate": 0.0,
        "converted_deal_value": 0.0,
    }


def test_growth_overview_api_does_not_expose_database_errors(
    analytics_db,
    monkeypatch,
):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(analytics_db))

    with TestClient(app) as client:
        def fail_growth_query(connection, dataset_id):
            assert connection is not None
            assert dataset_id == "analytics-test"
            raise sqlite3.OperationalError("private database path")

        monkeypatch.setattr(main_module, "get_growth_overview", fail_growth_query)
        response = client.get(
            "/api/analytics/growth",
            params={"dataset_id": "analytics-test"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to calculate growth overview."}
    assert "private database path" not in response.text
