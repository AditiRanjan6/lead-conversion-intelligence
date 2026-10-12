import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_connection, initialize_database
from app.models import Dataset
from app.schemas import (
    ActiveDatasetResponse,
    DatasetListResponse,
    DatasetResponse,
    FunnelAnalyticsResponse,
    GrowthOverviewResponse,
    SelectActiveDatasetRequest,
)
from app.services.datasets import (
    ensure_synthetic_dataset_registered,
    get_active_dataset,
    list_datasets,
    validate_dataset_id,
    select_active_dataset,
)
from app.services.analytics import get_funnel_analytics, get_growth_overview
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
    allow_methods=["GET", "PUT"],
    allow_headers=["Accept", "Content-Type"],
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
    )


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
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail="The configured active dataset is no longer registered.",
            ) from error
    return ActiveDatasetResponse(
        active_dataset=(
            _dataset_response(active_dataset, active_dataset.dataset_id)
            if active_dataset is not None
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
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return ActiveDatasetResponse(
        active_dataset=_dataset_response(
            selected_dataset,
            selected_dataset.dataset_id,
        )
    )


@app.get(
    "/api/analytics/growth",
    response_model=GrowthOverviewResponse,
    summary="Get dataset growth overview",
    description=(
        "Returns lead counts, qualification and conversion rates, and converted "
        "deal value for exactly one explicitly selected registered dataset. "
        "Rates are percentages rounded to two decimal places. Empty datasets "
        "return zero counts, rates, and deal value. The active dataset is not used."
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
) -> GrowthOverviewResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        with get_connection() as connection:
            metrics = get_growth_overview(connection, dataset_id)
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
        "selected registered dataset. Percentages use all dataset leads as the "
        "denominator; loss-stage percentages use all lost leads. Current-stage "
        "data cannot reconstruct historical transitions or exact drop-off counts."
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
) -> FunnelAnalyticsResponse:
    try:
        dataset_id = validate_dataset_id(dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        with get_connection() as connection:
            metrics = get_funnel_analytics(connection, dataset_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sqlite3.Error as error:
        logger.exception("Funnel analytics database query failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to calculate funnel analytics.",
        ) from error

    return FunnelAnalyticsResponse(**metrics)