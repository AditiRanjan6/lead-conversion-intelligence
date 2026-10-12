import pytest
from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import _get_cors_origins, app
from app.models import DatasetType
from app.services.datasets import register_dataset
from app.services.leads import count_leads


def test_health_endpoint_initializes_database_and_returns_ok(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert database_path.is_file()


def test_api_cors_allows_configured_local_frontend_origin(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.options(
            "/api/analytics/growth?dataset_id=synthetic-demo",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "accept",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_api_cors_allows_deployed_frontend_origin(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        response = client.options(
            "/api/datasets",
            headers={
                "Origin": "https://lead-conversion-intelligence-1.onrender.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "accept",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://lead-conversion-intelligence-1.onrender.com"
    )


def test_cors_origins_can_be_explicitly_configured(monkeypatch):
    monkeypatch.setenv(
        "LEAD_CONVERSION_CORS_ORIGINS",
        "https://dashboard.example, https://admin.example/",
    )

    assert _get_cors_origins() == [
        "https://dashboard.example",
        "https://admin.example",
    ]


def test_default_cors_origins_include_deployed_frontend(monkeypatch):
    monkeypatch.delenv("LEAD_CONVERSION_CORS_ORIGINS", raising=False)

    assert "https://lead-conversion-intelligence-1.onrender.com" in _get_cors_origins()


@pytest.mark.parametrize("configured_origins", ["", " , ", "*"])
def test_cors_configuration_rejects_empty_or_wildcard_origins(
    monkeypatch, configured_origins
):
    monkeypatch.setenv("LEAD_CONVERSION_CORS_ORIGINS", configured_origins)

    with pytest.raises(ValueError, match="explicit origins"):
        _get_cors_origins()


def test_startup_registers_synthetic_dataset_and_does_not_select_it(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        datasets = client.get("/api/datasets").json()["datasets"]
        active = client.get("/api/datasets/active")

    assert len(datasets) == 1
    assert datasets[0]["dataset_id"] == "synthetic-demo"
    assert datasets[0]["name"] == "Synthetic Demo Dataset"
    assert datasets[0]["dataset_type"] == "synthetic"
    assert datasets[0]["status"] == "inactive"
    assert datasets[0]["created_at"]
    assert active.status_code == 200
    assert active.json() == {"active_dataset": None}
    with get_connection(database_path) as connection:
        assert count_leads(connection, "synthetic-demo") > 0
        assert count_leads(connection, "synthetic-demo") == 120


def test_startup_recovers_missing_synthetic_dataset_without_changing_real_data(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app):
        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO datasets (dataset_id, name, dataset_type)
                VALUES (?, ?, ?)
                """,
                ("real-1", "Existing customer data", DatasetType.REAL.value),
            )
            connection.execute(
                """
                INSERT INTO application_settings (key, value)
                VALUES (?, ?)
                """,
                ("active_dataset_id", "real-1"),
            )
            connection.execute(
                "DELETE FROM leads WHERE dataset_id = ?",
                ("synthetic-demo",),
            )
            connection.execute(
                "DELETE FROM datasets WHERE dataset_id = ?",
                ("synthetic-demo",),
            )

    with TestClient(app) as client:
        datasets = client.get("/api/datasets").json()["datasets"]
        active = client.get("/api/datasets/active").json()["active_dataset"]

    by_id = {dataset["dataset_id"]: dataset for dataset in datasets}
    assert set(by_id) == {"real-1", "synthetic-demo"}
    assert by_id["real-1"]["name"] == "Existing customer data"
    assert by_id["real-1"]["dataset_type"] == "real"
    assert active["dataset_id"] == "real-1"


def test_active_dataset_selection_endpoints_validate_and_persist(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    with TestClient(app) as client:
        with get_connection(database_path) as connection:
            register_dataset(
                connection,
                "real-1",
                "Imported customers",
                DatasetType.REAL,
            )

        selected = client.put(
            "/api/datasets/active",
            json={"dataset_id": "real-1"},
        )
        active = client.get("/api/datasets/active")
        listing = client.get("/api/datasets")
        invalid = client.put(
            "/api/datasets/active",
            json={"dataset_id": "missing"},
        )
        malformed = client.put(
            "/api/datasets/active",
            json={"dataset_id": "not a valid id"},
        )
        malformed_newline = client.put(
            "/api/datasets/active",
            json={"dataset_id": "real-1\n"},
        )
        unchanged = client.get("/api/datasets/active")

    assert selected.status_code == 200
    assert selected.json()["active_dataset"]["dataset_id"] == "real-1"
    assert selected.json()["active_dataset"]["status"] == "active"
    assert active.json() == selected.json()
    listed = {dataset["dataset_id"]: dataset for dataset in listing.json()["datasets"]}
    assert listed["real-1"]["status"] == "active"
    assert listed["synthetic-demo"]["status"] == "inactive"
    assert invalid.status_code == 404
    assert "not registered" in invalid.json()["detail"]
    assert malformed.status_code == 422
    assert malformed_newline.status_code == 422
    assert unchanged.json()["active_dataset"]["dataset_id"] == "real-1"


def test_repeated_startup_does_not_duplicate_synthetic_registration(tmp_path, monkeypatch):
    database_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))

    for _ in range(2):
        with TestClient(app):
            pass

    with get_connection(database_path) as connection:
        dataset_count = connection.execute(
            "SELECT COUNT(*) AS count FROM datasets WHERE dataset_id = ?",
            ("synthetic-demo",),
        ).fetchone()["count"]
        lead_count = connection.execute(
            "SELECT COUNT(*) AS count FROM leads WHERE dataset_id = ?",
            ("synthetic-demo",),
        ).fetchone()["count"]

    assert dataset_count == 1
    assert lead_count == 120
