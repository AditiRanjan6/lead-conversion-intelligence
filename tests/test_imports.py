import sqlite3
import json

import pytest
from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app
from app.services.imports import ParsedImport, commit_import

_ADMIN_TOKEN = "test-only-admin-token"
_CSV = (
    "Name,Source,Campaign,Created At,Stage,Status,Qualified,Owner,Last Activity\n"
    "Jordan Lee,referral,Partner Network,2026-09-01T09:00:00Z,new,open,true,Casey,2026-09-02T09:00:00Z\n"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(tmp_path / "imports.sqlite3"))
    monkeypatch.setenv("LEAD_CONVERSION_ADMIN_TOKEN", _ADMIN_TOKEN)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, path, content=_CSV, *, data=None, headers=None):
    return client.post(
        path,
        data=data or {},
        files={"file": ("leads.csv", content, "text/csv")},
        headers=headers or {},
    )


def test_csv_preview_reports_valid_invalid_and_duplicate_rows(client):
    content = (
        _CSV
        + "Jordan Lee,referral,Partner Network,2026-09-01T09:00:00Z,new,open,true,Casey,2026-09-02T09:00:00Z\n"
        + "Invalid Lead,unknown,Campaign,2026-09-03T09:00:00Z,new,open,true,Casey,2026-09-03T10:00:00Z\n"
    )

    response = _upload(client, "/api/imports/preview", content)

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 1
    assert body["duplicate_rows"] == 1
    assert body["rejected_rows"] == 1
    assert body["errors"][0]["row_number"] == 3
    assert body["errors"][1]["row_number"] == 4
    assert body["sample_rows"][0]["name"] == "Jordan Lee"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            "Taylor Morgan,referral,Campaign,not-a-date,new,open,true,Casey,2026-09-02T09:00:00Z",
            "created_at must be an ISO 8601 timestamp",
        ),
        (
            "Taylor Morgan,referral,Campaign,2026-09-01T09:00:00Z,closed_won,converted,true,Casey,2026-09-02T09:00:00Z",
            "Converted leads require converted_at",
        ),
    ],
)
def test_csv_preview_reports_invalid_dates_numbers_and_outcomes(client, row, message):
    response = _upload(client, "/api/imports/preview", _CSV.splitlines()[0] + "\n" + row + "\n")

    assert response.status_code == 200
    assert response.json()["valid_rows"] == 0
    assert response.json()["rejected_rows"] == 1
    assert message in " ".join(response.json()["errors"][0]["messages"])


def test_csv_preview_rejects_non_numeric_deal_value(client):
    content = (
        "Name,Source,Campaign,Created At,Stage,Status,Qualified,Owner,Last Activity,Converted At,Deal Value\n"
        "Taylor Morgan,referral,Campaign,2026-09-01T09:00:00Z,closed_won,converted,true,Casey,"
        "2026-09-02T09:00:00Z,2026-09-03T09:00:00Z,not-a-number\n"
    )
    response = _upload(client, "/api/imports/preview", content)

    assert response.status_code == 200
    assert response.json()["rejected_rows"] == 1
    assert "deal_value must be a number" in response.json()["errors"][0]["messages"][0]


def test_csv_import_is_admin_gated_transactional_and_records_history(client):
    unauthorized = _upload(client, "/api/datasets/import")
    assert unauthorized.status_code == 401

    response = _upload(
        client,
        "/api/datasets/import",
        _CSV
        + "Bad Lead,not-a-source,Campaign,2026-09-03T09:00:00Z,new,open,false,Casey,2026-09-03T10:00:00Z\n",
        data={"dataset_name": "September leads"},
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["imported_rows"] == 1
    assert result["rejected_rows"] == 1
    dataset_id = result["dataset_id"]
    datasets = client.get("/api/datasets").json()["datasets"]
    imported_dataset = next(item for item in datasets if item["dataset_id"] == dataset_id)
    assert imported_dataset["name"] == "September leads"
    assert imported_dataset["dataset_type"] == "real"
    assert imported_dataset["lead_count"] == 1
    assert client.get("/api/imports", params={"dataset_id": dataset_id}).json()[0][
        "filename"
    ] == "leads.csv"
    assert client.get(
        "/api/leads",
        params={"dataset_id": dataset_id},
    ).json()["total"] == 1


def test_csv_import_deduplicates_against_the_existing_dataset(client):
    imported = _upload(
        client,
        "/api/datasets/import",
        data={"dataset_name": "Imported leads"},
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    dataset_id = imported.json()["dataset_id"]

    preview = _upload(
        client,
        "/api/imports/preview",
        data={"dataset_id": dataset_id},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["valid_rows"] == 0
    assert body["duplicate_rows"] == 1


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("leads.xlsx", b"not an excel workbook", 415),
        ("leads.csv", b"\xff\xfe", 422),
        ("leads.csv", b"", 422),
    ],
)
def test_csv_import_rejects_unsupported_or_malformed_files(client, filename, content, status):
    response = client.post(
        "/api/imports/preview",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == status


def test_csv_import_rejects_files_over_the_size_limit(client):
    response = client.post(
        "/api/imports/preview",
        files={"file": ("large.csv", b"x" * (5 * 1024 * 1024 + 1), "text/csv")},
    )
    assert response.status_code == 413


def test_csv_import_rejects_more_than_ten_thousand_rows(client):
    header = _CSV.splitlines()[0]
    row = _CSV.splitlines()[1]
    content = f"{header}\n" + (f"{row}\n" * 10_001)

    response = _upload(client, "/api/imports/preview", content)

    assert response.status_code == 422
    assert "10,000 data rows" in response.json()["detail"]


def test_import_history_requires_registered_dataset(client):
    response = client.get("/api/imports", params={"dataset_id": "not-registered"})
    assert response.status_code == 404


def test_commit_import_rolls_back_new_dataset_on_database_failure(tmp_path, monkeypatch):
    database_path = tmp_path / "rollback.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))
    with TestClient(app):
        parsed = ParsedImport(
            analysis={
                "headers": [],
                "suggested_mapping": {},
                "total_rows": 1,
                "valid_rows": 1,
                "rejected_rows": 0,
                "duplicate_rows": 0,
                "errors": [],
                "sample_rows": [],
            },
            records=[
                {
                    "lead_id": "rollback-lead",
                    "name": "Invalid state",
                    "acquisition_source": "referral",
                    "campaign": "Campaign",
                    "created_at": "2026-09-01T09:00:00Z",
                    "stage": "new",
                    "status": "converted",
                    "is_qualified": 0,
                    "assigned_owner": "Casey",
                    "last_activity_at": "2026-09-02T09:00:00Z",
                    "next_follow_up_at": None,
                    "converted_at": None,
                    "deal_value": None,
                }
            ],
            filename="bad.csv",
        )
        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(database_path) as connection:
                commit_import(connection, parsed, dataset_name="Must roll back")

    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM datasets WHERE name = ?",
            ("Must roll back",),
        ).fetchone()[0] == 0


def test_import_mapping_supports_alternate_column_names(client):
    csv_text = (
        "Full Name,Lead Source,Marketing Campaign,Created,Pipeline Stage,Lead Status,"
        "Is Qualified,Sales Owner,Last Activity\n"
        "Morgan Park,webinar,Spring,2026-09-01T09:00:00Z,new,open,yes,Sam,2026-09-02T09:00:00Z\n"
    )
    mapping = {
        "name": "Full Name",
        "acquisition_source": "Lead Source",
        "campaign": "Marketing Campaign",
        "created_at": "Created",
        "stage": "Pipeline Stage",
        "status": "Lead Status",
        "is_qualified": "Is Qualified",
        "assigned_owner": "Sales Owner",
        "last_activity_at": "Last Activity",
    }

    response = _upload(
        client,
        "/api/imports/preview",
        csv_text,
        data={"mapping": json.dumps(mapping)},
    )

    assert response.status_code == 200
    assert response.json()["valid_rows"] == 1


def test_csv_rows_with_extra_fields_are_reported_in_preview(client):
    content = _CSV.strip() + ",unexpected-value\n"

    response = _upload(client, "/api/imports/preview", content)

    assert response.status_code == 200
    assert response.json()["valid_rows"] == 0
    assert "more values" in response.json()["errors"][0]["messages"][0]
