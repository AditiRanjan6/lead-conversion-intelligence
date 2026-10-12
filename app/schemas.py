from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import DatasetType, LeadStage
from app.services.datasets import validate_dataset_id


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    dataset_type: DatasetType
    status: Literal["active", "inactive"]
    created_at: str


class DatasetListResponse(BaseModel):
    datasets: list[DatasetResponse]


class ActiveDatasetResponse(BaseModel):
    active_dataset: DatasetResponse | None


class GrowthOverviewResponse(BaseModel):
    total_leads: int = Field(
        description="All leads registered in the requested dataset."
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
        description="Converted leads divided by total leads, as a percentage rounded to 2 decimals."
    )
    qualification_rate: float = Field(
        description="Qualified leads divided by total leads, as a percentage rounded to 2 decimals."
    )
    converted_deal_value: float = Field(
        description="Sum of converted-lead deal values, rounded to 2 decimals."
    )


class FunnelStageMetricResponse(BaseModel):
    stage: LeadStage
    lead_count: int = Field(description="Leads currently recorded in this stage.")
    percentage_of_total: float = Field(
        description="Stage lead count divided by all leads in the dataset, as a percentage."
    )


class LostStageMetricResponse(BaseModel):
    stage: LeadStage
    lead_count: int = Field(description="Lost leads currently recorded in this stage.")
    percentage_of_lost_leads: float = Field(
        description="Lost leads in this stage divided by all lost leads, as a percentage."
    )


class LossAnalysisResponse(BaseModel):
    total_lost_leads: int = Field(description="Leads whose status is lost.")
    loss_rate: float = Field(
        description="Lost leads divided by all leads in the dataset, as a percentage."
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
