import sqlite3
import re

from app.models import Dataset, DatasetType

_ACTIVE_DATASET_SETTING = "active_dataset_id"
SYNTHETIC_DEMO_DATASET_ID = "synthetic-demo"
SYNTHETIC_DEMO_DATASET_NAME = "Synthetic Demo Dataset"
_DATASET_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def validate_dataset_id(dataset_id: str) -> str:
    if not isinstance(dataset_id, str) or _DATASET_ID_PATTERN.fullmatch(dataset_id) is None:
        raise ValueError(
            "Dataset ID must be 1-64 characters, start with a letter or digit, "
            "and contain only letters, digits, '.', '_' or '-'."
        )
    return dataset_id


def require_registered_dataset(
    connection: sqlite3.Connection,
    dataset_id: str,
) -> str:
    dataset_id = validate_dataset_id(dataset_id)
    row = connection.execute(
        "SELECT dataset_id FROM datasets WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Dataset {dataset_id!r} is not registered")
    return dataset_id


def _normalize_dataset_type(dataset_type: DatasetType | str) -> DatasetType:
    try:
        return DatasetType(dataset_type)
    except (TypeError, ValueError) as error:
        allowed_types = ", ".join(dataset_type.value for dataset_type in DatasetType)
        raise ValueError(f"Dataset type must be one of: {allowed_types}.") from error


def register_dataset(
    connection: sqlite3.Connection,
    dataset_id: str,
    name: str,
    dataset_type: DatasetType | str,
) -> Dataset:
    dataset_id = validate_dataset_id(dataset_id)
    dataset_type = _normalize_dataset_type(dataset_type)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Dataset name must not be empty.")

    connection.execute(
        """
        INSERT INTO datasets (dataset_id, name, dataset_type)
        VALUES (?, ?, ?)
        """,
        (dataset_id, name, dataset_type.value),
    )
    row = connection.execute(
        """
        SELECT dataset_id, name, dataset_type, created_at
        FROM datasets
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Dataset registration did not create a dataset")
    return _dataset_from_row(row)


def ensure_synthetic_dataset_registered(connection: sqlite3.Connection) -> Dataset:
    connection.execute(
        """
        INSERT INTO datasets (dataset_id, name, dataset_type)
        VALUES (?, ?, ?)
        ON CONFLICT(dataset_id) DO NOTHING
        """,
        (
            SYNTHETIC_DEMO_DATASET_ID,
            SYNTHETIC_DEMO_DATASET_NAME,
            DatasetType.SYNTHETIC.value,
        ),
    )
    row = connection.execute(
        """
        SELECT dataset_id, name, dataset_type, created_at
        FROM datasets
        WHERE dataset_id = ?
        """,
        (SYNTHETIC_DEMO_DATASET_ID,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Synthetic demo dataset registration failed")
    if row["dataset_type"] != DatasetType.SYNTHETIC.value:
        raise RuntimeError(
            f"Dataset ID {SYNTHETIC_DEMO_DATASET_ID!r} is already registered "
            "with a different dataset type"
        )
    return _dataset_from_row(row)


def list_datasets(connection: sqlite3.Connection) -> list[Dataset]:
    rows = connection.execute(
        """
        SELECT d.dataset_id, d.name, d.dataset_type, d.created_at,
            COUNT(l.lead_id) AS lead_count
        FROM datasets AS d
        LEFT JOIN leads AS l ON l.dataset_id = d.dataset_id
        GROUP BY d.dataset_id, d.name, d.dataset_type, d.created_at
        ORDER BY d.created_at, d.dataset_id
        """
    ).fetchall()
    return [_dataset_from_row(row) for row in rows]


def get_active_dataset(connection: sqlite3.Connection) -> Dataset | None:
    setting = connection.execute(
        "SELECT value FROM application_settings WHERE key = ?",
        (_ACTIVE_DATASET_SETTING,),
    ).fetchone()
    if setting is None:
        return None

    row = connection.execute(
        """
        SELECT dataset_id, name, dataset_type, created_at
        FROM datasets
        WHERE dataset_id = ?
        """,
        (setting["value"],),
    ).fetchone()
    if row is None:
        raise RuntimeError("The configured active dataset does not exist")
    return _dataset_from_row(row)


def select_active_dataset(connection: sqlite3.Connection, dataset_id: str) -> Dataset:
    dataset_id = validate_dataset_id(dataset_id)
    row = connection.execute(
        """
        SELECT dataset_id, name, dataset_type, created_at
        FROM datasets
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Dataset {dataset_id!r} is not registered")

    connection.execute(
        """
        INSERT INTO application_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (_ACTIVE_DATASET_SETTING, dataset_id),
    )
    return _dataset_from_row(row)


def rename_dataset(
    connection: sqlite3.Connection,
    dataset_id: str,
    name: str,
) -> Dataset:
    dataset_id = require_registered_dataset(connection, dataset_id)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Dataset name must not be empty.")
    if len(name.strip()) > 120:
        raise ValueError("Dataset name must be 120 characters or fewer.")
    connection.execute(
        "UPDATE datasets SET name = ? WHERE dataset_id = ?",
        (name.strip(), dataset_id),
    )
    row = connection.execute(
        """
        SELECT dataset_id, name, dataset_type, created_at
        FROM datasets
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Renamed dataset was not found")
    return _dataset_from_row(row)


def delete_dataset(connection: sqlite3.Connection, dataset_id: str) -> None:
    dataset_id = require_registered_dataset(connection, dataset_id)
    if dataset_id == SYNTHETIC_DEMO_DATASET_ID:
        raise ValueError("The built-in synthetic demo dataset cannot be deleted.")
    connection.execute(
        "DELETE FROM application_settings WHERE key = ? AND value = ?",
        (_ACTIVE_DATASET_SETTING, dataset_id),
    )
    connection.execute("DELETE FROM import_history WHERE dataset_id = ?", (dataset_id,))
    connection.execute("DELETE FROM leads WHERE dataset_id = ?", (dataset_id,))
    connection.execute("DELETE FROM datasets WHERE dataset_id = ?", (dataset_id,))


def _dataset_from_row(row: sqlite3.Row) -> Dataset:
    return Dataset(
        dataset_id=row["dataset_id"],
        name=row["name"],
        dataset_type=DatasetType(row["dataset_type"]),
        created_at=row["created_at"],
        lead_count=row["lead_count"] if "lead_count" in row.keys() else 0,
    )