from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models import (
    AcquisitionSource,
    DatasetType,
    LeadStage,
    LeadStatus,
)
from app.services.datasets import validate_dataset_id


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    dataset_type: DatasetType
    status: Literal["active", "inactive"]
    created_at: str
    lead_count: int


class DatasetListResponse(BaseModel):
    datasets: list[DatasetResponse]


class ActiveDatasetResponse(BaseModel):
    active_dataset: DatasetResponse | None


class GrowthOverviewResponse(BaseModel):
    total_leads: int = Field(
        description="All leads in the requested dataset matching the supplied filters."
    )
    qualified_leads: int = Field(
        description="Leads whose is_qualified flag is true."
    )
    converted_leads: int = Field(
        description="Leads whose status is converted."
    )
    lost_leads: int = Field(
        description="Leads whose status is lost."
    )
    conversion_rate: float = Field(
        description="Converted leads divided by matching leads, as a percentage rounded to 2 decimals."
    )
    qualification_rate: float = Field(
        description="Qualified leads divided by matching leads, as a percentage rounded to 2 decimals."
    )
    converted_deal_value: float = Field(
        description="Sum of matching converted-lead deal values, rounded to 2 decimals."
    )


class FunnelStageMetricResponse(BaseModel):
    stage: LeadStage
    lead_count: int = Field(
        description="Matching leads currently recorded in this stage."
    )
    percentage_of_total: float = Field(
        description="Stage lead count divided by all leads matching the filters, as a percentage."
    )


class LostStageMetricResponse(BaseModel):
    stage: LeadStage
    lead_count: int = Field(description="Lost leads currently recorded in this stage.")
    percentage_of_lost_leads: float = Field(
        description="Lost leads in this stage divided by all lost leads, as a percentage."
    )


class LossAnalysisResponse(BaseModel):
    total_lost_leads: int = Field(
        description="Matching leads whose status is lost."
    )
    loss_rate: float = Field(
        description="Lost leads divided by all leads matching the filters, as a percentage."
    )
    leads_by_stage: list[LostStageMetricResponse]


class FunnelAnalyticsResponse(BaseModel):
    dataset_id: str
    total_leads: int
    stage_distribution: list[FunnelStageMetricResponse]
    funnel: list[FunnelStageMetricResponse] = Field(
        description=(
            "Current-stage counts in pipeline order; percentages are of all leads, "
            "not historical stage-to-stage conversion rates."
        )
    )
    loss_analysis: LossAnalysisResponse
    data_limitations: list[str]


class SelectActiveDatasetRequest(BaseModel):
    dataset_id: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "A registered dataset ID: 1-64 characters, starting with a "
            "letter or digit and containing only letters, digits, '.', '_' or '-'."
        ),
    )

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_must_be_valid(cls, dataset_id: str) -> str:
        return validate_dataset_id(dataset_id)


class DatasetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("Dataset name must not be empty.")
        return name.strip()


class LeadWriteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    lead_id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    acquisition_source: AcquisitionSource
    campaign: str = Field(min_length=1, max_length=200)
    created_at: str
    stage: LeadStage
    status: LeadStatus
    is_qualified: bool
    assigned_owner: str = Field(min_length=1, max_length=120)
    last_activity_at: str
    next_follow_up_at: str | None = None
    converted_at: str | None = None
    deal_value: float | None = Field(default=None, gt=0)

    @field_validator("created_at", "last_activity_at")
    @classmethod
    def required_timestamps_are_utc(cls, value: str) -> str:
        return _normalize_api_timestamp(value)

    @field_validator("next_follow_up_at", "converted_at")
    @classmethod
    def optional_timestamps_are_utc(cls, value: str | None) -> str | None:
        return _normalize_api_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "LeadWriteRequest":
        if self.last_activity_at < self.created_at:
            raise ValueError("last_activity_at must not be before created_at.")
        if (
            self.next_follow_up_at is not None
            and self.next_follow_up_at < self.created_at
        ):
            raise ValueError("next_follow_up_at must not be before created_at.")
        if self.status is LeadStatus.OPEN:
            if self.stage in {LeadStage.CLOSED_WON, LeadStage.CLOSED_LOST}:
                raise ValueError("Open leads must use an open pipeline stage.")
            if self.converted_at is not None or self.deal_value is not None:
                raise ValueError("Open leads cannot have conversion time or deal value.")
        elif self.status is LeadStatus.CONVERTED:
            if self.stage is not LeadStage.CLOSED_WON:
                raise ValueError("Converted leads must use the closed_won stage.")
            if self.converted_at is None or self.deal_value is None:
                raise ValueError(
                    "Converted leads require converted_at and a positive deal_value."
                )
            if self.converted_at < self.created_at:
                raise ValueError("converted_at must not be before created_at.")
            if self.next_follow_up_at is not None:
                raise ValueError("Converted leads cannot have a next follow-up.")
        else:
            if self.stage is not LeadStage.CLOSED_LOST:
                raise ValueError("Lost leads must use the closed_lost stage.")
            if (
                self.converted_at is not None
                or self.deal_value is not None
                or self.next_follow_up_at is not None
            ):
                raise ValueError(
                    "Lost leads cannot have conversion time, deal value, or next follow-up."
                )
        return self


class LeadResponse(LeadWriteRequest):
    lead_id: str
    dataset_id: str


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    total: int
    page: int
    page_size: int
    filter_options: dict[str, list[str]]


class ImportRowError(BaseModel):
    row_number: int
    messages: list[str]


class ImportPreviewResponse(BaseModel):
    headers: list[str]
    suggested_mapping: dict[str, str]
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    errors: list[ImportRowError]
    sample_rows: list[dict[str, object]]


class ImportResultResponse(BaseModel):
    dataset_id: str
    import_id: str
    imported_rows: int
    rejected_rows: int
    duplicate_rows: int
    outcome: str


class ImportHistoryItem(BaseModel):
    import_id: str
    dataset_id: str
    filename: str
    imported_at: str
    total_rows: int
    imported_rows: int
    rejected_rows: int
    duplicate_rows: int
    outcome: str


def _normalize_api_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Timestamps must be ISO 8601 with a timezone.") from error
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a timezone (for example, Z).")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
