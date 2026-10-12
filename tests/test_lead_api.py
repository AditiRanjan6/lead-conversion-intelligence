import pytest
from fastapi.testclient import TestClient

from app.database import get_connection
from app.main import app
from app.models import DatasetType
from app.services.datasets import register_dataset

_ADMIN_TOKEN = "lead-test-token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "leads-api.sqlite3"
    monkeypatch.setenv("LEAD_CONVERSION_DB_PATH", str(database_path))
    monkeypatch.setenv("LEAD_CONVERSION_ADMIN_TOKEN", _ADMIN_TOKEN)
    with TestClient(app) as test_client:
        with get_connection(database_path) as connection:
            register_dataset(connection, "real-1", "Imported", DatasetType.REAL)
        yield test_client


def _lead(name="Avery Stone", **overrides):
    lead = {
        "name": name,
        "acquisition_source": "referral",
        "campaign": "Spring pipeline",
        "created_at": "2026-09-01T09:00:00Z",
        "stage": "new",
        "status": "open",
        "is_qualified": True,
        "assigned_owner": "Taylor",
        "last_activity_at": "2026-09-02T09:00:00Z",
        "next_follow_up_at": "2026-09-05T09:00:00Z",
        "converted_at": None,
        "deal_value": None,
    }
    return {**lead, **overrides}


def test_lead_crud_requires_admin_token_and_scopes_to_dataset(client):
    denied = client.post(
        "/api/leads",
        params={"dataset_id": "real-1"},
        json=_lead(),
    )
    assert denied.status_code == 401

    created = client.post(
        "/api/leads",
        params={"dataset_id": "real-1"},
        json=_lead(),
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert created.status_code == 201
    lead = created.json()
    assert lead["dataset_id"] == "real-1"

    listed = client.get(
        "/api/leads",
        params={"dataset_id": "real-1", "search": "Avery", "source": "referral"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["leads"][0]["lead_id"] == lead["lead_id"]
    assert client.get(
        "/api/leads",
        params={"dataset_id": "synthetic-demo", "search": lead["lead_id"]},
    ).json()["total"] == 0

    updated = client.put(
        f"/api/leads/{lead['lead_id']}",
        params={"dataset_id": "real-1"},
        json=_lead("Avery Stone Updated", lead_id=lead["lead_id"]),
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Avery Stone Updated"

    deleted = client.delete(
        f"/api/leads/{lead['lead_id']}",
        params={"dataset_id": "real-1"},
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/api/leads/{lead['lead_id']}",
        params={"dataset_id": "real-1"},
    ).status_code == 404


def test_lead_list_filters_sorting_and_pagination(client):
    for name, source, created_at in (
        ("Avery Stone", "referral", "2026-09-01T09:00:00Z"),
        ("Blake Morgan", "webinar", "2026-09-03T09:00:00Z"),
    ):
        response = client.post(
            "/api/leads",
            params={"dataset_id": "real-1"},
            json=_lead(
                name,
                acquisition_source=source,
                created_at=created_at,
                last_activity_at=created_at,
            ),
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert response.status_code == 201

    response = client.get(
        "/api/leads",
        params={
            "dataset_id": "real-1",
            "date_from": "2026-09-02",
            "date_to": "2026-09-03",
            "sort": "name",
            "direction": "asc",
            "page": 1,
            "page_size": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["leads"][0]["name"] == "Blake Morgan"


def test_lead_list_filters_qualified_boolean_and_sorts_campaign(client):
    for name, qualified, campaign in (
        ("Qualified Avery", True, "Zebra"),
        ("Unqualified Blake", False, "Alpha"),
    ):
        response = client.post(
            "/api/leads",
            params={"dataset_id": "real-1"},
            json=_lead(name, is_qualified=qualified, campaign=campaign),
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert response.status_code == 201

    qualified_response = client.get(
        "/api/leads",
        params={"dataset_id": "real-1", "qualified": "true"},
    )
    unqualified_response = client.get(
        "/api/leads",
        params={
            "dataset_id": "real-1",
            "qualified": "false",
            "sort": "campaign",
            "direction": "asc",
        },
    )

    assert qualified_response.status_code == 200
    assert qualified_response.json()["total"] == 1
    assert qualified_response.json()["leads"][0]["name"] == "Qualified Avery"
    assert unqualified_response.status_code == 200
    assert unqualified_response.json()["total"] == 1
    assert unqualified_response.json()["leads"][0]["name"] == "Unqualified Blake"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "converted", "stage": "closed_won"}, "require converted_at"),
        ({"created_at": "2026-09-01T09:00:00"}, "include a timezone"),
        ({"stage": "closed_lost"}, "open pipeline stage"),
    ],
)
def test_lead_create_validates_business_rules(client, overrides, message):
    response = client.post(
        "/api/leads",
        params={"dataset_id": "real-1"},
        json=_lead(**overrides),
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert response.status_code == 422
    assert message in str(response.json())


def test_dataset_management_renames_and_deletes_imported_dataset_only(client):
    denied = client.patch(
        "/api/datasets/real-1",
        json={"name": "New name"},
    )
    assert denied.status_code == 401

    renamed = client.patch(
        "/api/datasets/real-1",
        json={"name": "September customers"},
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "September customers"
    assert renamed.json()["lead_count"] == 0

    protected = client.delete(
        "/api/datasets/synthetic-demo",
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )
    assert protected.status_code == 409
    assert client.delete(
        "/api/datasets/real-1",
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    ).status_code == 204
    assert all(
        dataset["dataset_id"] != "real-1"
        for dataset in client.get("/api/datasets").json()["datasets"]
    )


def test_mutating_routes_fail_closed_when_admin_token_is_not_configured(
    client, monkeypatch
):
    monkeypatch.delenv("LEAD_CONVERSION_ADMIN_TOKEN", raising=False)

    response = client.delete(
        "/api/datasets/real-1",
        headers={"X-Admin-Token": _ADMIN_TOKEN},
    )

    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]
