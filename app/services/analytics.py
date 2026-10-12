import sqlite3
from typing import TypedDict

from app.models import LeadStage
from app.services.datasets import require_registered_dataset


class StageMetric(TypedDict):
    stage: str
    lead_count: int
    percentage_of_total: float


class LostStageMetric(TypedDict):
    stage: str
    lead_count: int
    percentage_of_lost_leads: float


class LossAnalysis(TypedDict):
    total_lost_leads: int
    loss_rate: float
    leads_by_stage: list[LostStageMetric]


class FunnelAnalyticsMetrics(TypedDict):
    dataset_id: str
    total_leads: int
    stage_distribution: list[StageMetric]
    funnel: list[StageMetric]
    loss_analysis: LossAnalysis
    data_limitations: list[str]


class GrowthOverviewMetrics(TypedDict):
    total_leads: int
    qualified_leads: int
    converted_leads: int
    lost_leads: int
    conversion_rate: float
    qualification_rate: float
    converted_deal_value: float


_FUNNEL_DATA_LIMITATIONS = [
    "Leads contain only their current stage; stage-transition history is not available.",
    (
        "Stage counts and percentages describe the current dataset snapshot and "
        "cannot establish historical transitions or exact drop-off counts."
    ),
    "The lead schema does not record loss reasons.",
]


def get_funnel_analytics(
    connection: sqlite3.Connection,
    dataset_id: str,
) -> FunnelAnalyticsMetrics:
    """Calculate current-stage funnel and loss metrics for one dataset."""

    dataset_id = require_registered_dataset(connection, dataset_id)
    rows = connection.execute(
        """
        SELECT
            stage,
            COUNT(*) AS lead_count,
            SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) AS lost_lead_count
        FROM leads
        WHERE dataset_id = ?
        GROUP BY stage
        """,
        (dataset_id,),
    ).fetchall()

    stage_counts = {stage: 0 for stage in LeadStage}
    lost_stage_counts = {stage: 0 for stage in LeadStage}
    for row in rows:
        stage = LeadStage(row["stage"])
        stage_counts[stage] = row["lead_count"]
        lost_stage_counts[stage] = row["lost_lead_count"]

    total_leads = sum(stage_counts.values())
    total_lost_leads = sum(lost_stage_counts.values())
    stage_metrics: list[StageMetric] = [
        {
            "stage": stage.value,
            "lead_count": stage_counts[stage],
            "percentage_of_total": (
                round(stage_counts[stage] / total_leads * 100, 2)
                if total_leads
                else 0.0
            ),
        }
        for stage in LeadStage
    ]
    lost_stage_metrics: list[LostStageMetric] = [
        {
            "stage": stage.value,
            "lead_count": lost_stage_counts[stage],
            "percentage_of_lost_leads": (
                round(lost_stage_counts[stage] / total_lost_leads * 100, 2)
                if total_lost_leads
                else 0.0
            ),
        }
        for stage in LeadStage
    ]

    return {
        "dataset_id": dataset_id,
        "total_leads": total_leads,
        "stage_distribution": stage_metrics,
        "funnel": stage_metrics,
        "loss_analysis": {
            "total_lost_leads": total_lost_leads,
            "loss_rate": (
                round(total_lost_leads / total_leads * 100, 2)
                if total_leads
                else 0.0
            ),
            "leads_by_stage": lost_stage_metrics,
        },
        "data_limitations": list(_FUNNEL_DATA_LIMITATIONS),
    }


def get_growth_overview(
    connection: sqlite3.Connection,
    dataset_id: str,
) -> GrowthOverviewMetrics:
    """Calculate core growth metrics for one registered dataset."""

    dataset_id = require_registered_dataset(connection, dataset_id)

    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total_leads,
            COALESCE(SUM(is_qualified), 0) AS qualified_leads,
            COALESCE(
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END),
                0
            ) AS converted_leads,
            COALESCE(
                SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END),
                0
            ) AS lost_leads,
            COALESCE(
                SUM(CASE
                    WHEN status = 'converted' THEN deal_value
                    ELSE 0
                END),
                0
            ) AS converted_deal_value
        FROM leads
        WHERE dataset_id = ?
        """,
        (dataset_id,),
    ).fetchone()

    if row is None:
        raise RuntimeError("Growth overview query returned no result")

    total_leads = row["total_leads"]
    qualified_leads = row["qualified_leads"]
    converted_leads = row["converted_leads"]

    return {
        "total_leads": total_leads,
        "qualified_leads": qualified_leads,
        "converted_leads": converted_leads,
        "lost_leads": row["lost_leads"],
        "conversion_rate": (
            round(converted_leads / total_leads * 100, 2)
            if total_leads
            else 0.0
        ),
        "qualification_rate": (
            round(qualified_leads / total_leads * 100, 2)
            if total_leads
            else 0.0
        ),
        "converted_deal_value": round(row["converted_deal_value"], 2),
    }
