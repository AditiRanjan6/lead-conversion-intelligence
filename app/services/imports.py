import csv
import io
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import TypedDict

from app.models import AcquisitionSource, LeadStage, LeadStatus
from app.services.datasets import require_registered_dataset

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
PREVIEW_SAMPLE_SIZE = 20
IMPORT_COLUMNS = (
    "lead_id",
    "name",
    "acquisition_source",
    "campaign",
    "created_at",
    "stage",
    "status",
    "is_qualified",
    "assigned_owner",
    "last_activity_at",
    "next_follow_up_at",
    "converted_at",
    "deal_value",
)
REQUIRED_COLUMNS = (
    "name",
    "acquisition_source",
    "campaign",
    "created_at",
    "stage",
    "status",
    "is_qualified",
    "assigned_owner",
    "last_activity_at",
)
_COLUMN_ALIASES = {
    "id": "lead_id",
    "leadid": "lead_id",
    "name": "name",
    "leadname": "name",
    "source": "acquisition_source",
    "acquisitionsource": "acquisition_source",
    "campaign": "campaign",
    "createdat": "created_at",
    "created": "created_at",
    "stage": "stage",
    "status": "status",
    "qualified": "is_qualified",
    "isqualified": "is_qualified",
    "owner": "assigned_owner",
    "assignedowner": "assigned_owner",
    "lastactivity": "last_activity_at",
    "lastactivityat": "last_activity_at",
    "nextfollowup": "next_follow_up_at",
    "nextfollowupat": "next_follow_up_at",
    "convertedat": "converted_at",
    "dealvalue": "deal_value",
}
_LEAD_INSERT = """
    INSERT INTO leads (
        lead_id, dataset_id, name, acquisition_source, campaign, created_at,
        stage, status, is_qualified, assigned_owner, last_activity_at,
        next_follow_up_at, converted_at, deal_value
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class RowIssue(TypedDict):
    row_number: int
    messages: list[str]


class ImportAnalysis(TypedDict):
    headers: list[str]
    suggested_mapping: dict[str, str]
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    errors: list[RowIssue]
    sample_rows: list[dict[str, object]]


@dataclass(frozen=True)
class ParsedImport:
    analysis: ImportAnalysis
    records: list[dict[str, object]]
    filename: str


def analyze_csv(
    connection: sqlite3.Connection,
    content: bytes,
    filename: str,
    mapping: dict[str, str] | None = None,
    dataset_id: str | None = None,
) -> ParsedImport:
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("CSV files must be 5 MB or smaller.")
    if not content:
        raise ValueError("The uploaded CSV file is empty.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV files must use UTF-8 encoding.") from error

    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    headers = reader.fieldnames
    if not headers or not any(header and header.strip() for header in headers):
        raise ValueError("The CSV file must contain a header row.")
    if len(headers) != len(set(headers)):
        raise ValueError("The CSV contains duplicate column headers.")
    if None in headers or any(not header.strip() for header in headers):
        raise ValueError("Every CSV column must have a non-empty header.")
    if dataset_id is not None:
        dataset_id = require_registered_dataset(connection, dataset_id)

    suggested_mapping = _suggest_mapping(headers)
    chosen_mapping = mapping if mapping is not None else suggested_mapping
    mapping_errors = _validate_mapping(chosen_mapping, headers)
    row_issues: list[RowIssue] = []
    parsed_records: list[dict[str, object]] = []
    valid_samples: list[dict[str, object]] = []
    seen_ids: dict[str, int] = {}
    seen_keys: dict[tuple[str, str, str, str], int] = {}
    existing_ids: set[str] = set()
    existing_keys: set[tuple[str, str, str, str]] = set()
    if dataset_id is not None:
        existing = connection.execute(
            """
            SELECT lead_id, name, acquisition_source, campaign, created_at
            FROM leads WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchall()
        existing_ids = {row["lead_id"] for row in existing}
        existing_keys = {
            _duplicate_key(row["name"], row["acquisition_source"], row["campaign"], row["created_at"])
            for row in existing
        }
    else:
        existing = connection.execute("SELECT lead_id FROM leads").fetchall()
        existing_ids = {row["lead_id"] for row in existing}

    total_rows = 0
    for row_number, row in enumerate(_iter_rows(reader), start=2):
        if row is None:
            continue
        extra_values = row.get(None)
        row_values = [value for key, value in row.items() if key is not None]
        if (
            not any(isinstance(value, str) and value.strip() for value in row_values)
            and not extra_values
        ):
            continue
        total_rows += 1
        if total_rows > MAX_IMPORT_ROWS:
            raise ValueError("CSV files may contain at most 10,000 data rows.")
        messages = list(mapping_errors)
        if extra_values:
            messages.append("Row has more values than the CSV header defines.")
        source_row = {
            target: (row.get(source) or "").strip()
            for target, source in chosen_mapping.items()
            if source in row and isinstance(row.get(source), str)
        }
        parsed: dict[str, object] | None = None
        if not messages:
            try:
                parsed = _parse_record(source_row)
            except ValueError as error:
                messages.extend(str(error).split("; "))

        if parsed is not None:
            lead_id = str(parsed["lead_id"])
            key = _duplicate_key(
                str(parsed["name"]),
                str(parsed["acquisition_source"]),
                str(parsed["campaign"]),
                str(parsed["created_at"]),
            )
            duplicate_of = seen_ids.get(lead_id)
            if duplicate_of is None:
                duplicate_of = seen_keys.get(key)
            if duplicate_of is not None:
                messages.append(f"Duplicate of row {duplicate_of}.")
            elif lead_id in existing_ids or key in existing_keys:
                messages.append("Duplicate lead already exists in this dataset.")
            else:
                seen_ids[lead_id] = row_number
                seen_keys[key] = row_number
                parsed_records.append(parsed)
                if len(valid_samples) < PREVIEW_SAMPLE_SIZE:
                    valid_samples.append({"row_number": row_number, **parsed})

        if messages:
            row_issues.append({"row_number": row_number, "messages": messages})

    duplicates = sum(
        1 for item in row_issues if any(message.startswith("Duplicate") for message in item["messages"])
    )
    rejected = len(row_issues) - duplicates
    analysis: ImportAnalysis = {
        "headers": list(headers),
        "suggested_mapping": suggested_mapping,
        "total_rows": total_rows,
        "valid_rows": len(parsed_records),
        "rejected_rows": rejected,
        "duplicate_rows": duplicates,
        "errors": row_issues[:200],
        "sample_rows": valid_samples,
    }
    return ParsedImport(
        analysis=analysis,
        records=parsed_records,
        filename=_safe_filename(filename),
    )


def commit_import(
    connection: sqlite3.Connection,
    parsed: ParsedImport,
    dataset_id: str | None = None,
    dataset_name: str | None = None,
) -> tuple[str, str]:
    if not parsed.records:
        raise ValueError("There are no valid, non-duplicate rows to import.")
    if dataset_id is not None:
        dataset_id = require_registered_dataset(connection, dataset_id)
        dataset = connection.execute(
            "SELECT dataset_type FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if dataset is None or dataset["dataset_type"] != "real":
            raise ValueError("Imports can only be appended to imported datasets.")
    else:
        if not isinstance(dataset_name, str) or not dataset_name.strip():
            raise ValueError("A dataset name is required for a new import.")
        if len(dataset_name.strip()) > 120:
            raise ValueError("Dataset name must be 120 characters or fewer.")
        dataset_id = f"import-{uuid.uuid4().hex}"
        connection.execute(
            "INSERT INTO datasets (dataset_id, name, dataset_type) VALUES (?, ?, 'real')",
            (dataset_id, dataset_name.strip()),
        )

    for record in parsed.records:
        connection.execute(
            _LEAD_INSERT,
            (
                record["lead_id"],
                dataset_id,
                record["name"],
                record["acquisition_source"],
                record["campaign"],
                record["created_at"],
                record["stage"],
                record["status"],
                record["is_qualified"],
                record["assigned_owner"],
                record["last_activity_at"],
                record["next_follow_up_at"],
                record["converted_at"],
                record["deal_value"],
            ),
        )
    rejected = parsed.analysis["rejected_rows"]
    duplicates = parsed.analysis["duplicate_rows"]
    outcome = "completed_with_rejections" if rejected or duplicates else "completed"
    import_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO import_history (
            import_id, dataset_id, filename, total_rows, imported_rows,
            rejected_rows, duplicate_rows, outcome
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_id,
            dataset_id,
            parsed.filename,
            parsed.analysis["total_rows"],
            len(parsed.records),
            rejected,
            duplicates,
            outcome,
        ),
    )
    return dataset_id, import_id


def _parse_record(source: dict[str, str]) -> dict[str, object]:
    missing = [
        column.replace("_", " ")
        for column in REQUIRED_COLUMNS
        if not source.get(column, "").strip()
    ]
    if missing:
        raise ValueError(f"Missing required value: {', '.join(missing)}.")

    try:
        source_value = AcquisitionSource(source["acquisition_source"]).value
    except ValueError as error:
        raise ValueError(
            "Acquisition source must be one of: "
            + ", ".join(item.value for item in AcquisitionSource)
            + "."
        ) from error
    try:
        stage = LeadStage(source["stage"]).value
    except ValueError as error:
        raise ValueError(
            "Stage must be one of: " + ", ".join(item.value for item in LeadStage) + "."
        ) from error
    try:
        status = LeadStatus(source["status"]).value
    except ValueError as error:
        raise ValueError(
            "Status must be one of: " + ", ".join(item.value for item in LeadStatus) + "."
        ) from error

    is_qualified = _parse_boolean(source["is_qualified"])
    created_at = _normalize_timestamp(source["created_at"], "created_at")
    last_activity_at = _normalize_timestamp(source["last_activity_at"], "last_activity_at")
    next_follow_up_at = _normalize_optional_timestamp(
        source.get("next_follow_up_at", ""), "next_follow_up_at"
    )
    converted_at = _normalize_optional_timestamp(
        source.get("converted_at", ""), "converted_at"
    )
    if last_activity_at < created_at:
        raise ValueError("last_activity_at must not be before created_at.")
    if next_follow_up_at is not None and next_follow_up_at < created_at:
        raise ValueError("next_follow_up_at must not be before created_at.")

    deal_value = _parse_optional_number(source.get("deal_value", ""))
    if status == LeadStatus.OPEN.value:
        if stage not in {
            LeadStage.NEW.value,
            LeadStage.CONTACTED.value,
            LeadStage.QUALIFIED.value,
            LeadStage.PROPOSAL.value,
            LeadStage.NEGOTIATION.value,
        }:
            raise ValueError("Open leads must use an open pipeline stage.")
        if converted_at is not None or deal_value is not None:
            raise ValueError("Open leads cannot have conversion time or deal value.")
    elif status == LeadStatus.CONVERTED.value:
        if stage != LeadStage.CLOSED_WON.value:
            raise ValueError("Converted leads must use the closed_won stage.")
        if converted_at is None or deal_value is None or deal_value <= 0:
            raise ValueError(
                "Converted leads require converted_at and a positive deal_value."
            )
        if converted_at < created_at:
            raise ValueError("converted_at must not be before created_at.")
        if next_follow_up_at is not None:
            raise ValueError("Converted leads cannot have a next follow-up.")
    else:
        if stage != LeadStage.CLOSED_LOST.value:
            raise ValueError("Lost leads must use the closed_lost stage.")
        if converted_at is not None or deal_value is not None or next_follow_up_at is not None:
            raise ValueError(
                "Lost leads cannot have conversion time, deal value, or next follow-up."
            )

    name = source["name"].strip()
    campaign = source["campaign"].strip()
    owner = source["assigned_owner"].strip()
    if len(name) > 200 or len(campaign) > 200 or len(owner) > 120:
        raise ValueError("Name/campaign are limited to 200 characters; owner to 120.")
    lead_id = source.get("lead_id", "").strip() or str(uuid.uuid4())
    if len(lead_id) > 64:
        raise ValueError("lead_id must be 64 characters or fewer.")
    return {
        "lead_id": lead_id,
        "name": name,
        "acquisition_source": source_value,
        "campaign": campaign,
        "created_at": created_at,
        "stage": stage,
        "status": status,
        "is_qualified": int(is_qualified),
        "assigned_owner": owner,
        "last_activity_at": last_activity_at,
        "next_follow_up_at": next_follow_up_at,
        "converted_at": converted_at,
        "deal_value": deal_value,
    }


def _parse_boolean(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("is_qualified must be true/false, yes/no, or 1/0.")


def _parse_optional_number(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError("deal_value must be a number.") from error
    if not math.isfinite(number):
        raise ValueError("deal_value must be a finite number.")
    return number


def _normalize_optional_timestamp(value: str, field: str) -> str | None:
    return _normalize_timestamp(value, field) if value.strip() else None


def _normalize_timestamp(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone (for example, Z).")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _duplicate_key(name: str, source: str, campaign: str, created_at: str) -> tuple[str, str, str, str]:
    return name.strip().casefold(), source.casefold(), campaign.strip().casefold(), created_at


def _suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = "".join(character.lower() for character in header if character.isalnum())
        target = _COLUMN_ALIASES.get(normalized)
        if target is not None and target not in mapping:
            mapping[target] = header
    return mapping


def _validate_mapping(mapping: dict[str, str], headers: list[str]) -> list[str]:
    errors = [
        f"Mapping target {target!r} is not a supported lead field."
        for target in mapping
        if target not in IMPORT_COLUMNS
    ]
    errors.extend(
        f"Mapping for {target!r} must reference a CSV header."
        for target, header in mapping.items()
        if header not in headers
    )
    errors.extend(
        f"CSV headers are mapped to more than one field: {header!r}."
        for header in {item for item in mapping.values() if list(mapping.values()).count(item) > 1}
    )
    missing = sorted(set(REQUIRED_COLUMNS) - set(mapping))
    if missing:
        errors.append(f"Map required fields: {', '.join(missing)}.")
    return errors


def _safe_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").split("/")[-1].strip()
    return basename[:180] or "uploaded.csv"


def _iter_rows(reader: csv.DictReader[str]):
    try:
        yield from reader
    except csv.Error as error:
        raise ValueError("The uploaded file is not a well-formed CSV.") from error
