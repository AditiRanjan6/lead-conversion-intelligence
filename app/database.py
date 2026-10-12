import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH_ENV = "LEAD_CONVERSION_DB_PATH"
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "lead_conversion.sqlite3"
BUSY_TIMEOUT_MS = 5_000

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS datasets (
        dataset_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        dataset_type TEXT NOT NULL CHECK (dataset_type IN ('synthetic', 'real')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_history (
        import_id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
        filename TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        total_rows INTEGER NOT NULL,
        imported_rows INTEGER NOT NULL,
        rejected_rows INTEGER NOT NULL,
        duplicate_rows INTEGER NOT NULL,
        outcome TEXT NOT NULL CHECK (
            outcome IN ('completed', 'completed_with_rejections')
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leads (
        lead_id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
        name TEXT NOT NULL,
        acquisition_source TEXT NOT NULL CHECK (
            acquisition_source IN (
                'paid_search', 'organic_search', 'referral',
                'webinar', 'partner', 'outbound'
            )
        ),
        campaign TEXT NOT NULL,
        created_at TEXT NOT NULL,
        stage TEXT NOT NULL CHECK (
            stage IN (
                'new', 'contacted', 'qualified', 'proposal',
                'negotiation', 'closed_won', 'closed_lost'
            )
        ),
        status TEXT NOT NULL CHECK (status IN ('open', 'converted', 'lost')),
        is_qualified INTEGER NOT NULL CHECK (is_qualified IN (0, 1)),
        assigned_owner TEXT NOT NULL,
        last_activity_at TEXT NOT NULL,
        next_follow_up_at TEXT,
        converted_at TEXT,
        deal_value REAL,
        CHECK (created_at GLOB '????-??-??T??:??:??Z'),
        CHECK (last_activity_at GLOB '????-??-??T??:??:??Z'),
        CHECK (
            next_follow_up_at IS NULL
            OR next_follow_up_at GLOB '????-??-??T??:??:??Z'
        ),
        CHECK (
            converted_at IS NULL
            OR converted_at GLOB '????-??-??T??:??:??Z'
        ),
        CHECK (last_activity_at >= created_at),
        CHECK (next_follow_up_at IS NULL OR next_follow_up_at >= created_at),
        CHECK (
            (
                status = 'open'
                AND stage IN ('new', 'contacted', 'qualified', 'proposal', 'negotiation')
                AND converted_at IS NULL
                AND deal_value IS NULL
            )
            OR (
                status = 'converted'
                AND stage = 'closed_won'
                AND converted_at IS NOT NULL
                AND converted_at >= created_at
                AND deal_value > 0
                AND next_follow_up_at IS NULL
            )
            OR (
                status = 'lost'
                AND stage = 'closed_lost'
                AND converted_at IS NULL
                AND deal_value IS NULL
                AND next_follow_up_at IS NULL
            )
        )
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_created "
    "ON leads (dataset_id, created_at, lead_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_stage "
    "ON leads (dataset_id, stage)",
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_source "
    "ON leads (dataset_id, acquisition_source)",
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_last_activity "
    "ON leads (dataset_id, last_activity_at)",
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_follow_up "
    "ON leads (dataset_id, next_follow_up_at)",
    "CREATE INDEX IF NOT EXISTS idx_leads_dataset_converted "
    "ON leads (dataset_id, converted_at)",
)


def get_database_path(database_path: str | Path | None = None) -> Path:
    if database_path is None:
        configured_path = os.environ.get(DATABASE_PATH_ENV)
        if configured_path is not None:
            if not configured_path.strip():
                raise ValueError(f"{DATABASE_PATH_ENV} must not be empty")
            database_path = configured_path.strip()
        else:
            database_path = DEFAULT_DATABASE_PATH
    return Path(database_path).expanduser().resolve()


@contextmanager
def get_connection(database_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    path = get_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1_000)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path | None = None) -> None:
    with get_connection(database_path) as connection:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
        for statement in _INDEX_STATEMENTS:
            connection.execute(statement)