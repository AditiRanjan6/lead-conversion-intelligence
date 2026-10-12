import sqlite3
import uuid
from datetime import date, timedelta

from app.models import AcquisitionSource, Lead, LeadStage, LeadStatus
from app.services.datasets import require_registered_dataset

_LEAD_COLUMNS = """
    lead_id, dataset_id, name, acquisition_source, campaign, created_at,
    stage, status, is_qualified, assigned_owner, last_activity_at,
    next_follow_up_at, converted_at, deal_value
"""
_SORT_COLUMNS = {
    "created_at": "created_at",
    "name": "name COLLATE NOCASE",
    "stage": "stage",
    "status": "status",
    "source": "acquisition_source",
    "owner": "assigned_owner COLLATE NOCASE",
    "campaign": "campaign COLLATE NOCASE",
}


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


def get_leads_page(
    connection: sqlite3.Connection,
    dataset_id: str,
    *,
    search: str = "",
    stage: str | None = None,
    status: str | None = None,
    qualified: bool | None = None,
    source: str | None = None,
    owner: str | None = None,
    campaign: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Lead], int, dict[str, list[str]]]:
    dataset_id = require_registered_dataset(connection, dataset_id)
    if sort not in _SORT_COLUMNS:
        raise ValueError(f"Sort must be one of: {', '.join(_SORT_COLUMNS)}.")
    if direction not in {"asc", "desc"}:
        raise ValueError("Sort direction must be 'asc' or 'desc'.")
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("Page must be positive and page_size must be from 1 to 100.")

    clauses = ["dataset_id = ?"]
    parameters: list[object] = [dataset_id]
    for column, value in (
        ("stage", stage),
        ("status", status),
        ("acquisition_source", source),
        ("assigned_owner", owner),
        ("campaign", campaign),
    ):
        if value:
            clauses.append(f"{column} = ?")
            parameters.append(value)
    if qualified is not None:
        clauses.append("is_qualified = ?")
        parameters.append(int(qualified))
    if search.strip():
        clauses.append(
            "(lead_id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' "
            "OR campaign LIKE ? ESCAPE '\\' OR assigned_owner LIKE ? ESCAPE '\\')"
        )
        escaped = _escape_like(search.strip())
        parameters.extend([f"%{escaped}%"] * 4)
    if date_from:
        clauses.append("created_at >= ?")
        parameters.append(_date_bound(date_from, end=False))
    if date_to:
        clauses.append("created_at < ?")
        parameters.append(_date_bound(date_to, end=True))

    where_clause = " AND ".join(clauses)
    count_row = connection.execute(
        f"SELECT COUNT(*) AS total FROM leads WHERE {where_clause}",
        parameters,
    ).fetchone()
    if count_row is None:
        raise RuntimeError("Lead count query returned no result")
    offset = (page - 1) * page_size
    rows = connection.execute(
        f"""
        SELECT {_LEAD_COLUMNS}
        FROM leads
        WHERE {where_clause}
        ORDER BY {_SORT_COLUMNS[sort]} {direction.upper()}, lead_id
        LIMIT ? OFFSET ?
        """,
        [*parameters, page_size, offset],
    ).fetchall()
    options: dict[str, list[str]] = {
        "stage": [item.value for item in LeadStage],
        "status": [item.value for item in LeadStatus],
        "source": [item.value for item in AcquisitionSource],
    }
    for key, column in (("owner", "assigned_owner"), ("campaign", "campaign")):
        distinct_rows = connection.execute(
            f"""
            SELECT DISTINCT {column} AS value FROM leads
            WHERE dataset_id = ? ORDER BY value COLLATE NOCASE
            """,
            (dataset_id,),
        ).fetchall()
        options[key] = [row["value"] for row in distinct_rows]
    return [_lead_from_row(row) for row in rows], count_row["total"], options


def get_lead(
    connection: sqlite3.Connection,
    dataset_id: str,
    lead_id: str,
) -> Lead | None:
    dataset_id = require_registered_dataset(connection, dataset_id)
    row = connection.execute(
        f"""
        SELECT {_LEAD_COLUMNS} FROM leads
        WHERE dataset_id = ? AND lead_id = ?
        """,
        (dataset_id, lead_id),
    ).fetchone()
    return _lead_from_row(row) if row is not None else None


def create_lead(
    connection: sqlite3.Connection,
    dataset_id: str,
    values: dict[str, object],
) -> Lead:
    dataset_id = require_registered_dataset(connection, dataset_id)
    lead_id = str(values.get("lead_id") or uuid.uuid4())
    try:
        connection.execute(
            """
            INSERT INTO leads (
                lead_id, dataset_id, name, acquisition_source, campaign, created_at,
                stage, status, is_qualified, assigned_owner, last_activity_at,
                next_follow_up_at, converted_at, deal_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                dataset_id,
                values["name"],
                _enum_value(values["acquisition_source"]),
                values["campaign"],
                values["created_at"],
                _enum_value(values["stage"]),
                _enum_value(values["status"]),
                int(bool(values["is_qualified"])),
                values["assigned_owner"],
                values["last_activity_at"],
                values["next_follow_up_at"],
                values["converted_at"],
                values["deal_value"],
            ),
        )
    except sqlite3.IntegrityError as error:
        raise ValueError("Lead could not be created; verify its ID and status fields.") from error
    created = get_lead(connection, dataset_id, lead_id)
    if created is None:
        raise RuntimeError("Created lead was not found")
    return created


def update_lead(
    connection: sqlite3.Connection,
    dataset_id: str,
    lead_id: str,
    values: dict[str, object],
) -> Lead | None:
    dataset_id = require_registered_dataset(connection, dataset_id)
    try:
        cursor = connection.execute(
            """
            UPDATE leads SET
                name = ?, acquisition_source = ?, campaign = ?, created_at = ?,
                stage = ?, status = ?, is_qualified = ?, assigned_owner = ?,
                last_activity_at = ?, next_follow_up_at = ?, converted_at = ?,
                deal_value = ?
            WHERE dataset_id = ? AND lead_id = ?
            """,
            (
                values["name"],
                _enum_value(values["acquisition_source"]),
                values["campaign"],
                values["created_at"],
                _enum_value(values["stage"]),
                _enum_value(values["status"]),
                int(bool(values["is_qualified"])),
                values["assigned_owner"],
                values["last_activity_at"],
                values["next_follow_up_at"],
                values["converted_at"],
                values["deal_value"],
                dataset_id,
                lead_id,
            ),
        )
    except sqlite3.IntegrityError as error:
        raise ValueError("Lead could not be updated; verify its status fields.") from error
    return get_lead(connection, dataset_id, lead_id) if cursor.rowcount else None


def delete_lead(
    connection: sqlite3.Connection,
    dataset_id: str,
    lead_id: str,
) -> bool:
    dataset_id = require_registered_dataset(connection, dataset_id)
    cursor = connection.execute(
        "DELETE FROM leads WHERE dataset_id = ? AND lead_id = ?",
        (dataset_id, lead_id),
    )
    return cursor.rowcount > 0


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


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _date_bound(value: str, *, end: bool) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Date filters must use YYYY-MM-DD.") from error
    if end:
        parsed += timedelta(days=1)
    return f"{parsed.isoformat()}T00:00:00Z"
