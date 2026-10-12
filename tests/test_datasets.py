import pytest

from app.database import get_connection, initialize_database
from app.models import DatasetType
from app.services.datasets import (
    ensure_synthetic_dataset_registered,
    get_active_dataset,
    list_datasets,
    register_dataset,
    select_active_dataset,
)


def test_active_dataset_requires_explicit_selection(tmp_path):
    database_path = tmp_path / "datasets.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        synthetic = register_dataset(
            connection, "synthetic-1", "Synthetic leads", DatasetType.SYNTHETIC
        )
        register_dataset(connection, "real-1", "Real leads", DatasetType.REAL)

        assert synthetic.dataset_type is DatasetType.SYNTHETIC
        assert get_active_dataset(connection) is None

        selected = select_active_dataset(connection, "real-1")
        active = get_active_dataset(connection)

    assert selected.dataset_id == "real-1"
    assert active is not None
    assert active.dataset_type is DatasetType.REAL


def test_selecting_unregistered_dataset_fails_without_changing_selection(tmp_path):
    database_path = tmp_path / "datasets.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        register_dataset(connection, "synthetic-1", "Synthetic leads", DatasetType.SYNTHETIC)
        select_active_dataset(connection, "synthetic-1")

        with pytest.raises(ValueError, match="not registered"):
            select_active_dataset(connection, "missing")

        active = get_active_dataset(connection)

    assert active is not None
    assert active.dataset_id == "synthetic-1"


def test_synthetic_registration_is_idempotent_and_preserves_real_datasets(tmp_path):
    database_path = tmp_path / "datasets.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        register_dataset(connection, "real-1", "Customer import", DatasetType.REAL)
        first = ensure_synthetic_dataset_registered(connection)
        second = ensure_synthetic_dataset_registered(connection)
        datasets = list_datasets(connection)

    assert first.dataset_id == second.dataset_id == "synthetic-demo"
    assert first.dataset_type is DatasetType.SYNTHETIC
    assert len([dataset for dataset in datasets if dataset.dataset_id == "synthetic-demo"]) == 1
    assert any(
        dataset.dataset_id == "real-1"
        and dataset.name == "Customer import"
        and dataset.dataset_type is DatasetType.REAL
        for dataset in datasets
    )


@pytest.mark.parametrize(
    ("dataset_id", "dataset_type", "message"),
    [
        ("contains spaces", DatasetType.REAL, "Dataset ID"),
        ("valid-id", "unsupported", "Dataset type"),
    ],
)
def test_register_dataset_validates_id_and_type(tmp_path, dataset_id, dataset_type, message):
    database_path = tmp_path / "datasets.sqlite3"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        with pytest.raises(ValueError, match=message):
            register_dataset(connection, dataset_id, "Example", dataset_type)