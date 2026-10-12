import sqlite3

from app.models import AcquisitionSource, Lead, LeadStage, LeadStatus
from app.services.datasets import require_registered_dataset

_LEAD_COLUMNS = """
    lead_id, dataset_id, name, acquisition_source, campaign, created_at,
    stage, status, is_qualified, assigned_owner, last_activity_at,
    next_follow_up_at, converted_at, deal_value
"""


def get_leads(connection: sqlite3.Connection, dataset_id: str) -> list[Lead]:
    dataset_id = require_registered_dataset(connection, dataset_id)
    rows = connection.execute(
        f"""
        SELECT {_LEAD_COLUMNS}
        FROM leads
        WHERE dataset_id = ?
        ORDER BY created_at, lead_id
        """,
        (dataset_id,),
    ).fetchall()
    return [_lead_from_row(row) for row in rows]


def count_leads(connection: sqlite3.Connection, dataset_id: str) -> int:
    dataset_id = require_registered_dataset(connection, dataset_id)
    row = connection.execute(
        "SELECT COUNT(*) AS lead_count FROM leads WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Lead count query returned no result")
    return row["lead_count"]


def _lead_from_row(row: sqlite3.Row) -> Lead:
    return Lead(
        lead_id=row["lead_id"],
        dataset_id=row["dataset_id"],
        name=row["name"],
        acquisition_source=AcquisitionSource(row["acquisition_source"]),
        campaign=row["campaign"],
        created_at=row["created_at"],
        stage=LeadStage(row["stage"]),
        status=LeadStatus(row["status"]),
        is_qualified=bool(row["is_qualified"]),
        assigned_owner=row["assigned_owner"],
        last_activity_at=row["last_activity_at"],
        next_follow_up_at=row["next_follow_up_at"],
        converted_at=row["converted_at"],
        deal_value=row["deal_value"],
    )
