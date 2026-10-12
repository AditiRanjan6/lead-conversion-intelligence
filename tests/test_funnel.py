import pytest
from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from app.models import LeadStage
from app.services.analytics import get_funnel_analytics
from app.services.datasets import register_dataset, select_active_dataset


@pytest.fixture
def funnel_db(tmp_path):
    db_path = tmp_path / "funnel_test.sqlite3"
    initialize_database(db_path)

    with get_connection(db_path) as connection:
        register_dataset(
            connection,
            dataset_id="funnel-test",
            name="Funnel Test",
            dataset_type="real",
        )
        register_dataset(
            connection,
            dataset_id="other-funnel",
            name="Other Funnel",
            dataset_type="real",
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
                    "funnel-1", "funnel-test", "Fictional Lead 1",
                    "paid_search", "Campaign A", "2026-10-01T10:00:00Z",
                    "new", "open", 0, "Owner A",
                    "2026-10-01T10:00:00Z", None, None, None,
                ),
                (
                    "funnel-2", "funnel-test", "Fictional Lead 2",
                    "organic_search", "Campaign B", "2026-10-02T10:00:00Z",
                    "new", "open", 0, "Owner A",
                    "2026-10-02T10:00:00Z", None, None, None,
                ),
                (
                    "funnel-3", "funnel-test", "Fictional Lead 3",
                    "referral", "Campaign C", "2026-10-03T10:00:00Z",
                    "contacted", "open", 0, "Owner B",
                    "2026-10-03T10:00:00Z", None, None, None,
                ),
                (
                    "funnel-4", "funnel-test", "Fictional Lead 4",
                    "webinar", "Campaign D", "2026-10-04T10:00:00Z",
                    "qualified", "open", 1, "Owner B",
                    "2026-10-04T10:00:00Z", None, None, None,
                ),
                (
                    "funnel-5", "funnel-test", "Fictional Lead 5",
                    "outbound", "Campaign E", "2026-10-05T10:00:00Z",
                    "closed_lost", "lost", 0, "Owner C",
                    "2026-10-05T10:00:00Z", None, None, None,
                ),
                (
                    "other-funnel-1", "other-funnel", "Other Fictional Lead",
                    "partner", "Other Campaign", "2026-10-06T10:00:00Z",
                    "closed_won", "converted", 1, "Owner D",
                    "2026-10-06T10:00:00Z", None,
                    "2026-10-06T10:00:00Z", 1000.0,
                ),
            ],
        )

    return db_path


def test_funnel_service_returns_ordered_stage_and_loss_metrics(funnel_db):
    with get_connection(funnel_db) as connection:
        result = get_funnel_analytics(connection, "funnel-test")

    expected_stages = [stage.value for stage in LeadStage]
    expected_counts = [2, 1, 1, 0, 0, 0, 1]
    assert result["total_leads"] == 5
    assert [item["stage"] for item in result["stage_distribution"]] == expected_stages
    assert [item["lead_count"] for item in result["stage_distribution"]] == expected_counts
    assert [item["percentage_of_total"] for item in result["stage_distribution"]] == [
        40.0, 20.0, 20.0, 0.0, 0.0, 0.0, 20.0,
    ]
    assert result["funnel"] == result["stage_distribution"]
    assert result["loss_analysis"]["total_lost_leads"] == 1
    assert result["loss_analysis"]["loss_rate"] == 20.0
    assert [item["stage"] for item in result["loss_analysis"]["leads_by_stage"]] == expected_stages
    assert [item["lead_count"] for item in result["loss_analysis"]["leads_by_stage"]] == [
        0, 0, 0, 0, 0, 0, 1,
    ]
    assert result["loss_analysis"]["leads_by_stage"][-1][
        "percentage_of_lost_leads"
    ] == 100.0
    assert any("historical transitions" in limit for limit in result["data_limitations"])
    assert any("drop-off counts" in limit for limit in result["data_limitations"])


def test_funnel_api_isolates_dataset_and_does_not_mutate_leads_or_active_selection(
    funnel_db, monkeypatch
):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(funnel_db))
    with TestClient(app) as client:
        with get_connection(funnel_db) as connection:
            select_active_dataset(connection, "other-funnel")
            before = connection.execute(
                "SELECT * FROM leads ORDER BY dataset_id, lead_id"
            ).fetchall()

        response = client.get(
            "/api/analytics/funnel",
            params={"dataset_id": "funnel-test"},
        )

    with get_connection(funnel_db) as connection:
        after = connection.execute(
            "SELECT * FROM leads ORDER BY dataset_id, lead_id"
        ).fetchall()
        active_dataset = connection.execute(
            "SELECT value FROM application_settings WHERE key = ?",
            ("active_dataset_id",),
        ).fetchone()["value"]

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == "funnel-test"
    assert body["total_leads"] == 5
    assert body["loss_analysis"]["total_lost_leads"] == 1
    assert set(body) == {
        "dataset_id",
        "total_leads",
        "stage_distribution",
        "funnel",
        "loss_analysis",
        "data_limitations",
    }
    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    assert active_dataset == "other-funnel"


def test_funnel_api_requires_valid_registered_dataset(funnel_db, monkeypatch):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(funnel_db))
    with TestClient(app) as client:
        missing = client.get("/api/analytics/funnel")
        blank = client.get("/api/analytics/funnel", params={"dataset_id": ""})
        malformed = client.get(
            "/api/analytics/funnel",
            params={"dataset_id": "bad id"},
        )
        unknown = client.get(
            "/api/analytics/funnel",
            params={"dataset_id": "not-registered"},
        )

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert malformed.status_code == 422
    assert unknown.status_code == 404


def test_funnel_api_returns_zero_metrics_for_empty_dataset(funnel_db, monkeypatch):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(funnel_db))
    with get_connection(funnel_db) as connection:
        register_dataset(
            connection,
            dataset_id="empty-funnel",
            name="Empty Funnel",
            dataset_type="real",
        )

    with TestClient(app) as client:
        response = client.get(
            "/api/analytics/funnel",
            params={"dataset_id": "empty-funnel"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_leads"] == 0
    assert body["loss_analysis"]["total_lost_leads"] == 0
    assert body["loss_analysis"]["loss_rate"] == 0.0
    assert [item["lead_count"] for item in body["stage_distribution"]] == [0] * 7
    assert [item["percentage_of_total"] for item in body["funnel"]] == [0.0] * 7
    assert [
        item["percentage_of_lost_leads"]
        for item in body["loss_analysis"]["leads_by_stage"]
    ] == [0.0] * 7


def test_funnel_endpoint_works_for_isolated_synthetic_demo_dataset(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "isolated_funnel.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.get(
            "/api/analytics/funnel",
            params={"dataset_id": "synthetic-demo"},
        )
        active = client.get("/api/datasets/active")

    assert response.status_code == 200
    assert response.json()["dataset_id"] == "synthetic-demo"
    assert response.json()["total_leads"] == 120
    assert sum(
        item["lead_count"] for item in response.json()["stage_distribution"]
    ) == 120
    assert active.json() == {"active_dataset": None}
