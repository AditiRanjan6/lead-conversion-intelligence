import sqlite3
from dataclasses import replace

import pytest

from app.database import get_connection, initialize_database
from app.models import AcquisitionSource, DatasetType, Lead, LeadStage, LeadStatus
from app.services.datasets import (
    SYNTHETIC_DEMO_DATASET_ID,
    ensure_synthetic_dataset_registered,
    register_dataset,
    select_active_dataset,
)
from app.services.leads import count_leads, get_leads
from app.services.synthetic_leads import (
    SYNTHETIC_LEAD_COUNT,
    generate_synthetic_leads,
    seed_synthetic_leads,
)


def test_synthetic_generation_is_deterministic_and_varied():
    first = generate_synthetic_leads()
    second = generate_synthetic_leads()

    assert len(first) == SYNTHETIC_LEAD_COUNT
    assert first == second
    assert len({lead.acquisition_source for lead in first}) > 1
    assert len({lead.campaign for lead in first}) > 1
    assert len({lead.stage for lead in first}) > 1
    assert len({lead.assigned_owner for lead in first}) > 1
    assert all(lead.dataset_id == SYNTHETIC_DEMO_DATASET_ID for lead in first)
    assert all(lead.name.startswith("Demo Lead ") for lead in first)


def test_seeding_is_idempotent_and_does_not_overwrite_existing_records(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        assert seed_synthetic_leads(connection) == SYNTHETIC_LEAD_COUNT
        original = connection.execute(
            "SELECT lead_id FROM leads ORDER BY lead_id LIMIT 1"
        ).fetchone()["lead_id"]
        connection.execute(
            "UPDATE leads SET name = ? WHERE lead_id = ?",
            ("Preserved existing synthetic record", original),
        )

        assert seed_synthetic_leads(connection) == 0
        saved_name = connection.execute(
            "SELECT name FROM leads WHERE lead_id = ?",
            (original,),
        ).fetchone()["name"]

    assert saved_name == "Preserved existing synthetic record"


def test_seeding_only_creates_synthetic_records_and_does_not_activate_dataset(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        register_dataset(connection, "real-1", "Existing customers", DatasetType.REAL)
        seed_synthetic_leads(connection)

        synthetic_count = count_leads(connection, SYNTHETIC_DEMO_DATASET_ID)
        real_count = count_leads(connection, "real-1")
        registered_data = connection.execute(
            """
            SELECT DISTINCT dataset_id
            FROM leads
            """
        ).fetchall()
        active = connection.execute(
            "SELECT value FROM application_settings WHERE key = ?",
            ("active_dataset_id",),
        ).fetchone()

    assert synthetic_count == SYNTHETIC_LEAD_COUNT
    assert real_count == 0
    assert {row["dataset_id"] for row in registered_data} == {
        SYNTHETIC_DEMO_DATASET_ID
    }
    assert active is None


def test_converted_and_unconverted_lead_fields_are_consistent(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        seed_synthetic_leads(connection)
        leads = get_leads(connection, SYNTHETIC_DEMO_DATASET_ID)

    converted_leads = [lead for lead in leads if lead.status is LeadStatus.CONVERTED]
    assert converted_leads
    for lead in leads:
        if lead.status is LeadStatus.CONVERTED:
            assert lead.stage is LeadStage.CLOSED_WON
            assert lead.converted_at is not None
            assert lead.deal_value is not None and lead.deal_value > 0
            assert lead.next_follow_up_at is None
            assert lead.converted_at.endswith("Z")
        else:
            assert lead.converted_at is None
            assert lead.deal_value is None
        if lead.status is LeadStatus.LOST:
            assert lead.stage is LeadStage.CLOSED_LOST
            assert lead.next_follow_up_at is None
        if lead.next_follow_up_at is not None:
            assert lead.status is LeadStatus.OPEN
            assert lead.next_follow_up_at.endswith("Z")
        assert lead.created_at.endswith("Z")
        assert lead.last_activity_at.endswith("Z")


def test_retrieval_and_counts_are_isolated_to_explicit_registered_dataset(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        register_dataset(connection, "real-1", "Existing customers", DatasetType.REAL)
        seed_synthetic_leads(connection)
        _insert_real_fixture_lead(connection)

        synthetic_leads = get_leads(connection, SYNTHETIC_DEMO_DATASET_ID)
        real_leads = get_leads(connection, "real-1")
        synthetic_count = count_leads(connection, SYNTHETIC_DEMO_DATASET_ID)
        real_count = count_leads(connection, "real-1")

    assert synthetic_count == SYNTHETIC_LEAD_COUNT
    assert len(synthetic_leads) == synthetic_count
    assert all(lead.dataset_id == SYNTHETIC_DEMO_DATASET_ID for lead in synthetic_leads)
    assert real_count == len(real_leads) == 1
    assert real_leads[0].lead_id == "real-fixture-1"
    assert real_leads[0].dataset_id == "real-1"


@pytest.mark.parametrize("dataset_id", ["bad id", "missing-dataset"])
def test_lead_queries_reject_invalid_or_unregistered_dataset_ids(tmp_path, dataset_id):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        with pytest.raises(ValueError):
            get_leads(connection, dataset_id)
        with pytest.raises(ValueError):
            count_leads(connection, dataset_id)


def test_lead_queries_reject_missing_dataset_id(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        with pytest.raises(ValueError, match="Dataset ID"):
            get_leads(connection, "")
        with pytest.raises(ValueError, match="Dataset ID"):
            count_leads(connection, "")


def test_seed_refuses_missing_or_real_reserved_dataset(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        with pytest.raises(ValueError, match="not registered"):
            seed_synthetic_leads(connection)

        register_dataset(
            connection,
            SYNTHETIC_DEMO_DATASET_ID,
            "Reserved ID misregistered as real",
            DatasetType.REAL,
        )
        with pytest.raises(RuntimeError, match="not a synthetic dataset"):
            seed_synthetic_leads(connection)


def test_lead_table_enforces_dataset_foreign_key_and_outcome_consistency(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        register_dataset(connection, "real-1", "Test data", DatasetType.REAL)
        fixture = _real_fixture_lead()

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert_lead(connection, replace(fixture, dataset_id="missing"))
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert_lead(
                connection,
                replace(
                    fixture,
                    lead_id="invalid-conversion",
                    status=LeadStatus.CONVERTED,
                    converted_at="2025-01-02T00:00:00Z",
                    deal_value=5_000,
                ),
            )


def test_explicit_dataset_selection_does_not_change_lead_query_scope(tmp_path):
    database_path = tmp_path / "leads.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        ensure_synthetic_dataset_registered(connection)
        register_dataset(connection, "real-1", "Existing customers", DatasetType.REAL)
        seed_synthetic_leads(connection)
        select_active_dataset(connection, "real-1")

        leads = get_leads(connection, SYNTHETIC_DEMO_DATASET_ID)
        active = connection.execute(
            "SELECT value FROM application_settings WHERE key = ?",
            ("active_dataset_id",),
        ).fetchone()["value"]

    assert active == "real-1"
    assert len(leads) == SYNTHETIC_LEAD_COUNT
    assert all(lead.dataset_id == SYNTHETIC_DEMO_DATASET_ID for lead in leads)


def _insert_real_fixture_lead(connection):
    _insert_lead(connection, _real_fixture_lead())


def _real_fixture_lead() -> Lead:
    return Lead(
        lead_id="real-fixture-1",
        dataset_id="real-1",
        name="Temporary Test Fixture",
        acquisition_source=AcquisitionSource.REFERRAL,
        campaign="Test Fixture Only",
        created_at="2025-01-01T00:00:00Z",
        stage=LeadStage.CONTACTED,
        status=LeadStatus.OPEN,
        is_qualified=False,
        assigned_owner="Fixture Owner",
        last_activity_at="2025-01-02T00:00:00Z",
        next_follow_up_at="2025-01-03T00:00:00Z",
        converted_at=None,
        deal_value=None,
    )


def _insert_lead(connection: sqlite3.Connection, fixture: Lead) -> None:
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
            fixture.lead_id,
            fixture.dataset_id,
            fixture.name,
            fixture.acquisition_source.value,
            fixture.campaign,
            fixture.created_at,
            fixture.stage.value,
            fixture.status.value,
            int(fixture.is_qualified),
            fixture.assigned_owner,
            fixture.last_activity_at,
            fixture.next_follow_up_at,
            fixture.converted_at,
            fixture.deal_value,
        ),
    )
