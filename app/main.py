import logging
import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_connection, initialize_database
from app.models import Dataset, Lead, LeadStage, LeadStatus, AcquisitionSource
from app.schemas import (
    ActiveDatasetResponse,
    DatasetListResponse,
    DatasetRenameRequest,
    DatasetResponse,
    FunnelAnalyticsResponse,
    GrowthOverviewResponse,
    ImportHistoryItem,
    ImportPreviewResponse,
    ImportResultResponse,
    LeadListResponse,
    LeadResponse,
    LeadWriteRequest,
    SelectActiveDatasetRequest,
)
from app.services.datasets import (
    ensure_synthetic_dataset_registered,
    get_active_dataset,
    list_datasets,
    rename_dataset,
    delete_dataset,
    validate_dataset_id,
    select_active_dataset,
)
from app.services.analytics import get_funnel_analytics, get_growth_overview
from app.services.imports import (
    MAX_IMPORT_BYTES,
    analyze_csv,
    commit_import,
)
from app.services.leads import (
    count_leads,
    create_lead,
    delete_lead,
    get_lead,
    get_leads_page,
    update_lead,
)
from app.services.synthetic_leads import seed_synthetic_leads

logger = logging.getLogger(__name__)
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://lead-conversion-intelligence-1.onrender.com",
)


def _get_cors_origins() -> list[str]:
    configured_origins = os.environ.get("LEAD_CONVERSION_CORS_ORIGINS")
    if configured_origins is None:
        return list(_DEFAULT_CORS_ORIGINS)

    origins = [
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip()
    ]
    if not origins or "*" in origins:
        raise ValueError(
            "LEAD_CONVERSION_CORS_ORIGINS must contain one or more explicit origins."
        )
    return origins


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        initialize_database()
        with get_connection() as connection:
            ensure_synthetic_dataset_registered(connection)
            seed_synthetic_leads(connection)
    except Exception:
        logger.exception("Application database initialization failed")
        raise
    yield


app = FastAPI(
    title="Lead Conversion Intelligence",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Accept", "Content-Type", "X-Admin-Token"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    with get_connection() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}


def _dataset_response(dataset: Dataset, active_dataset_id: str | None) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        dataset_type=dataset.dataset_type,
        status="active" if dataset.dataset_id == active_dataset_id else "inactive",
        created_at=dataset.created_at,
        lead_count=dataset.lead_count,
    )


def _require_admin_token(
    token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    configured_token = os.environ.get("LEAD_CONVERSION_ADMIN_TOKEN")
    if configured_token is None or not configured_token.strip():
        raise HTTPException(
            status_code=503,
            detail="Administrative operations are disabled until an admin token is configured.",
        )
    if token is None or not hmac.compare_digest(token, configured_token):
        raise HTTPException(status_code=401, detail="A valid admin token is required.")


def _read_mapping(value: str | None) -> dict[str, str] | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="Column mapping must be valid JSON.") from error
    if not isinstance(parsed, dict) or any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in parsed.items()
    ):
        raise HTTPException(
            status_code=422,
            detail="Column mapping must map lead field names to CSV header names.",
        )
    return parsed


async def _read_csv_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only .csv files are supported.")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="CSV files must be 5 MB or smaller.")
    return content, filename


@app.get("/api/datasets", response_model=DatasetListResponse)
def datasets_endpoint() -> DatasetListResponse:
    with get_connection() as connection:
        try:
            active_dataset = get_active_dataset(connection)
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail="The configured active dataset is no longer registered.",
            ) from error
        datasets = list_datasets(connection)
    active_dataset_id = active_dataset.dataset_id if active_dataset is not None else None
    return DatasetListResponse(
        datasets=[
            _dataset_response(dataset, active_dataset_id)
            for dataset in datasets
        ]
    )


@app.get("/api/datasets/active", response_model=ActiveDatasetResponse)
def active_dataset_endpoint() -> ActiveDatasetResponse:
    with get_connection() as connection:
        try:
            active_dataset = get_active_dataset(connection)
            response_dataset = (
                Dataset(
                    dataset_id=active_dataset.dataset_id,
                    name=active_dataset.name,
                    dataset_type=active_dataset.dataset_type,
                    created_at=active_dataset.created_at,
                    lead_count=count_leads(connection, active_dataset.dataset_id),
                )
                if active_dataset is not None
                else None
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail="The configured active dataset is no longer registered.",
            ) from error
    return ActiveDatasetResponse(
        active_dataset=(
            _dataset_response(response_dataset, response_dataset.dataset_id)
            if response_dataset is not None
            else None
        )
    )


@app.put("/api/datasets/active", response_model=ActiveDatasetResponse)
def select_active_dataset_endpoint(
    request: SelectActiveDatasetRequest,
) -> ActiveDatasetResponse:
    with get_connection() as connection:
        try:
            selected_dataset = select_active_dataset(connection, request.dataset_id)
            response_dataset = Dataset(
                dataset_id=selected_dataset.dataset_id,
                name=selected_dataset.name,
                dataset_type=selected_dataset.dataset_type,
                created_at=selected_dataset.created_at,
                lead_count=count_leads(connection, selected_dataset.dataset_id),
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return ActiveDatasetResponse(
        active_dataset=_dataset_response(
            response_dataset,
            selected_dataset.dataset_id,
        )
    )


@app.patch(
    "/api/datasets/{dataset_id}",
    response_model=DatasetResponse,
    dependencies=[Depends(_require_admin_token)],
)
def rename_dataset_endpoint(
    dataset_id: str,
    request: DatasetRenameRequest,
) -> DatasetResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        with get_connection() as connection:
            dataset = rename_dataset(connection, dataset_id, request.name)
            active = get_active_dataset(connection)
            dataset = Dataset(
                dataset_id=dataset.dataset_id,
                name=dataset.name,
                dataset_type=dataset.dataset_type,
                created_at=dataset.created_at,
                lead_count=count_leads(connection, dataset.dataset_id),
            )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _dataset_response(dataset, active.dataset_id if active else None)


@app.delete(
    "/api/datasets/{dataset_id}",
    status_code=204,
    dependencies=[Depends(_require_admin_token)],
)
def delete_dataset_endpoint(dataset_id: str) -> None:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        with get_connection() as connection:
            delete_dataset(connection, dataset_id)
    except ValueError as error:
        if "not registered" in str(error):
            raise HTTPException(status_code=404, detail=str(error)) from error
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post(
    "/api/imports/preview",
    response_model=ImportPreviewResponse,
    summary="Validate a CSV without storing it",
)
async def preview_csv_import_endpoint(
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
    dataset_id: Annotated[str | None, Form()] = None,
) -> ImportPreviewResponse:
    content, filename = await _read_csv_upload(file)
    column_mapping = _read_mapping(mapping)
    if dataset_id is not None:
        try:
            dataset_id = validate_dataset_id(dataset_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        with get_connection() as connection:
            parsed = analyze_csv(
                connection,
                content,
                filename,
                column_mapping,
                dataset_id,
            )
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return ImportPreviewResponse(**parsed.analysis)


@app.post(
    "/api/datasets/import",
    response_model=ImportResultResponse,
    status_code=201,
    dependencies=[Depends(_require_admin_token)],
    summary="Import validated CSV records into a new or existing dataset",
)
async def import_csv_endpoint(
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
    dataset_id: Annotated[str | None, Form()] = None,
    dataset_name: Annotated[str | None, Form()] = None,
) -> ImportResultResponse:
    content, filename = await _read_csv_upload(file)
    column_mapping = _read_mapping(mapping)
    if dataset_id is not None:
        try:
            dataset_id = validate_dataset_id(dataset_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        with get_connection() as connection:
            parsed = analyze_csv(
                connection,
                content,
                filename,
                column_mapping,
                dataset_id,
            )
            imported_dataset_id, import_id = commit_import(
                connection,
                parsed,
                dataset_id,
                dataset_name,
            )
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail=(
                "The import was rolled back because one or more records conflict "
                "with dataset constraints."
            ),
        ) from error
    except sqlite3.Error as error:
        logger.exception("CSV import transaction failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to complete the CSV import.",
        ) from error
    return ImportResultResponse(
        dataset_id=imported_dataset_id,
        import_id=import_id,
        imported_rows=len(parsed.records),
        rejected_rows=parsed.analysis["rejected_rows"],
        duplicate_rows=parsed.analysis["duplicate_rows"],
        outcome=(
            "completed_with_rejections"
            if parsed.analysis["rejected_rows"] or parsed.analysis["duplicate_rows"]
            else "completed"
        ),
    )


@app.get("/api/imports", response_model=list[ImportHistoryItem])
def import_history_endpoint(
    dataset_id: Annotated[str, Query(min_length=1)],
) -> list[ImportHistoryItem]:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        with get_connection() as connection:
            registered = connection.execute(
                "SELECT dataset_id FROM datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            if registered is None:
                raise HTTPException(status_code=404, detail="Dataset is not registered.")
            rows = connection.execute(
                """
                SELECT import_id, dataset_id, filename, imported_at, total_rows,
                    imported_rows, rejected_rows, duplicate_rows, outcome
                FROM import_history
                WHERE dataset_id = ?
                ORDER BY imported_at DESC, import_id
                """,
                (dataset_id,),
            ).fetchall()
    except sqlite3.Error as error:
        logger.exception("Import history query failed")
        raise HTTPException(status_code=500, detail="Unable to read import history.") from error
    return [ImportHistoryItem(**dict(row)) for row in rows]


@app.get("/api/leads", response_model=LeadListResponse)
def leads_endpoint(
    dataset_id: Annotated[str, Query(min_length=1)],
    search: str = "",
    stage: LeadStage | None = None,
    status: LeadStatus | None = None,
    qualified: bool | None = None,
    source: AcquisitionSource | None = None,
    owner: str | None = None,
    campaign: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> LeadListResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must not be after date_to.")
        with get_connection() as connection:
            leads, total, filter_options = get_leads_page(
                connection,
                dataset_id,
                search=search,
                stage=stage.value if stage else None,
                status=status.value if status else None,
                qualified=qualified,
                source=source.value if source else None,
                owner=owner,
                campaign=campaign,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                direction=direction.lower(),
                page=page,
                page_size=page_size,
            )
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return LeadListResponse(
        leads=[LeadResponse(**asdict(lead)) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
        filter_options=filter_options,
    )


@app.get("/api/leads/{lead_id}", response_model=LeadResponse)
def lead_detail_endpoint(
    lead_id: str,
    dataset_id: Annotated[str, Query(min_length=1)],
) -> LeadResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
        with get_connection() as connection:
            lead = get_lead(connection, dataset_id, lead_id)
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead was not found in this dataset.")
    return LeadResponse(**asdict(lead))


@app.post(
    "/api/leads",
    response_model=LeadResponse,
    status_code=201,
    dependencies=[Depends(_require_admin_token)],
)
def create_lead_endpoint(
    dataset_id: Annotated[str, Query(min_length=1)],
    request: LeadWriteRequest,
) -> LeadResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
        with get_connection() as connection:
            lead = create_lead(connection, dataset_id, request.model_dump())
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 409
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return LeadResponse(**asdict(lead))


@app.put(
    "/api/leads/{lead_id}",
    response_model=LeadResponse,
    dependencies=[Depends(_require_admin_token)],
)
def update_lead_endpoint(
    lead_id: str,
    dataset_id: Annotated[str, Query(min_length=1)],
    request: LeadWriteRequest,
) -> LeadResponse:
    if request.lead_id is not None and request.lead_id != lead_id:
        raise HTTPException(status_code=422, detail="Body lead_id must match the URL.")
    try:
        dataset_id = validate_dataset_id(dataset_id)
        with get_connection() as connection:
            lead = update_lead(
                connection,
                dataset_id,
                lead_id,
                request.model_dump(),
            )
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 409
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead was not found in this dataset.")
    return LeadResponse(**asdict(lead))


@app.delete(
    "/api/leads/{lead_id}",
    status_code=204,
    dependencies=[Depends(_require_admin_token)],
)
def delete_lead_endpoint(
    lead_id: str,
    dataset_id: Annotated[str, Query(min_length=1)],
) -> None:
    try:
        dataset_id = validate_dataset_id(dataset_id)
        with get_connection() as connection:
            deleted = delete_lead(connection, dataset_id, lead_id)
    except ValueError as error:
        status_code = 404 if "not registered" in str(error) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead was not found in this dataset.")


@app.get(
    "/api/analytics/growth",
    response_model=GrowthOverviewResponse,
    summary="Get dataset growth overview",
    description=(
        "Returns lead counts, qualification and conversion rates, and converted "
        "deal value for exactly one explicitly selected registered dataset. "
        "Optional stage, status, source, qualification, and created-date filters "
        "are applied before calculating every metric. Rates are percentages rounded "
        "to two decimal places. Empty result sets return zero metrics. The active "
        "dataset is not used."
    ),
)
def growth_overview_endpoint(
    dataset_id: Annotated[
        str,
        Query(
            description=(
                "Required registered dataset ID. Must start with a letter or "
                "digit and contain only letters, digits, '.', '_' or '-'."
            )
        ),
    ],
    stage: LeadStage | None = None,
    status: LeadStatus | None = None,
    source: AcquisitionSource | None = None,
    qualified: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> GrowthOverviewResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _validate_analytics_date_range(date_from, date_to)

    try:
        with get_connection() as connection:
            metrics = get_growth_overview(
                connection,
                dataset_id,
                stage=stage,
                status=status,
                source=source,
                qualified=qualified,
                date_from=date_from,
                date_to=date_to,
            )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sqlite3.Error as error:
        logger.exception("Growth overview database query failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate growth overview.",
        ) from error

    return GrowthOverviewResponse(**metrics)


@app.get(
    "/api/analytics/funnel",
    response_model=FunnelAnalyticsResponse,
    summary="Get funnel and loss intelligence",
    description=(
        "Returns current-stage counts and percentages for exactly one explicitly "
        "selected registered dataset. Optional stage, status, source, qualification, "
        "and created-date filters are applied before calculating every metric. "
        "Percentages use all matching leads as the denominator; loss-stage "
        "percentages use all matching lost leads. Current-stage data cannot "
        "reconstruct historical transitions or exact drop-off counts."
    ),
)
def funnel_analytics_endpoint(
    dataset_id: Annotated[
        str,
        Query(
            description=(
                "Required registered dataset ID. Must start with a letter or "
                "digit and contain only letters, digits, '.', '_' or '-'."
            )
        ),
    ],
    stage: LeadStage | None = None,
    status: LeadStatus | None = None,
    source: AcquisitionSource | None = None,
    qualified: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> FunnelAnalyticsResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _validate_analytics_date_range(date_from, date_to)

    try:
        with get_connection() as connection:
            metrics = get_funnel_analytics(
                connection,
                dataset_id,
                stage=stage,
                status=status,
                source=source,
                qualified=qualified,
                date_from=date_from,
                date_to=date_to,
            )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sqlite3.Error as error:
        logger.exception("Funnel analytics database query failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate funnel analytics.",
        ) from error

    return FunnelAnalyticsResponse(**metrics)


def _validate_analytics_date_range(
    date_from: date | None,
    date_to: date | None,
) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from must be on or before date_to.",
        )