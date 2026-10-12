import random
import sqlite3
from datetime import datetime, timedelta, timezone

from app.models import AcquisitionSource, Lead, LeadStage, LeadStatus
from app.services.datasets import SYNTHETIC_DEMO_DATASET_ID

SYNTHETIC_SEED = 20261011
SYNTHETIC_LEAD_COUNT = 120
_REFERENCE_TIME = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
_CAMPAIGNS = {
    AcquisitionSource.PAID_SEARCH: (
        "Demo Search - Brand",
        "Demo Search - Industry",
        "Demo Search - General",
    ),
    AcquisitionSource.ORGANIC_SEARCH: (
        "Demo SEO - Product Guide",
        "Demo SEO - Comparison Pages",
    ),
    AcquisitionSource.REFERRAL: (
        "Demo Referral - Customer Network",
        "Demo Referral - Advisor Network",
    ),
    AcquisitionSource.WEBINAR: (
        "Demo Webinar - Operations",
        "Demo Webinar - Growth",
    ),
    AcquisitionSource.PARTNER: (
        "Demo Partner - Integration",
        "Demo Partner - Reseller",
    ),
    AcquisitionSource.OUTBOUND: (
        "Demo Outbound - Mid-Market",
        "Demo Outbound - Enterprise",
    ),
}
_STAGE_OUTCOMES = (
    (LeadStage.NEW, LeadStatus.OPEN, 18),
    (LeadStage.CONTACTED, LeadStatus.OPEN, 18),
    (LeadStage.QUALIFIED, LeadStatus.OPEN, 19),
    (LeadStage.PROPOSAL, LeadStatus.OPEN, 15),
    (LeadStage.NEGOTIATION, LeadStatus.OPEN, 10),
    (LeadStage.CLOSED_WON, LeadStatus.CONVERTED, 13),
    (LeadStage.CLOSED_LOST, LeadStatus.LOST, 7),
)
_OWNERS = ("Demo Owner A", "Demo Owner B", "Demo Owner C", "Demo Owner D")


def generate_synthetic_leads() -> list[Lead]:
    generator = random.Random(SYNTHETIC_SEED)
    leads: list[Lead] = []
    outcomes = [
        (stage, status)
        for stage, status, weight in _STAGE_OUTCOMES
        for _ in range(weight)
    ]
    sources = tuple(_CAMPAIGNS)

    for index in range(1, SYNTHETIC_LEAD_COUNT + 1):
        stage, status = generator.choice(outcomes)
        source = generator.choice(sources)
        created_at = _REFERENCE_TIME - timedelta(
            days=generator.randint(0, 365),
            hours=generator.randint(0, 23),
        )
        created_seconds = int((_REFERENCE_TIME - created_at).total_seconds())

        if status is LeadStatus.CONVERTED:
            converted_at = created_at + timedelta(
                seconds=generator.randint(0, created_seconds)
            )
            last_activity_at = converted_at + timedelta(
                seconds=generator.randint(
                    0,
                    int((_REFERENCE_TIME - converted_at).total_seconds()),
                )
            )
            next_follow_up_at = None
            deal_value = float(generator.randrange(1_500, 60_000, 250))
        elif status is LeadStatus.LOST:
            converted_at = None
            last_activity_at = created_at + timedelta(
                seconds=generator.randint(0, created_seconds)
            )
            next_follow_up_at = None
            deal_value = None
        else:
            converted_at = None
            last_activity_at = created_at + timedelta(
                seconds=generator.randint(0, created_seconds)
            )
            next_follow_up_at = (
                _REFERENCE_TIME + timedelta(days=generator.randint(1, 45))
                if generator.random() < 0.72
                else None
            )
            deal_value = None

        is_qualified = stage in {
            LeadStage.QUALIFIED,
            LeadStage.PROPOSAL,
            LeadStage.NEGOTIATION,
            LeadStage.CLOSED_WON,
        } or (status is LeadStatus.LOST and generator.random() < 0.7)
        if stage in {LeadStage.NEW, LeadStage.CONTACTED} and generator.random() < 0.2:
            is_qualified = True

        leads.append(
            Lead(
                lead_id=f"{SYNTHETIC_DEMO_DATASET_ID}-{index:04d}",
                dataset_id=SYNTHETIC_DEMO_DATASET_ID,
                name=f"Demo Lead {index:04d}",
                acquisition_source=source,
                campaign=generator.choice(_CAMPAIGNS[source]),
                created_at=_format_utc(created_at),
                stage=stage,
                status=status,
                is_qualified=is_qualified,
                assigned_owner=generator.choice(_OWNERS),
                last_activity_at=_format_utc(last_activity_at),
                next_follow_up_at=(
                    _format_utc(next_follow_up_at)
                    if next_follow_up_at is not None
                    else None
                ),
                converted_at=(
                    _format_utc(converted_at) if converted_at is not None else None
                ),
                deal_value=deal_value,
            )
        )
    return leads


def seed_synthetic_leads(connection: sqlite3.Connection) -> int:
    dataset = connection.execute(
        "SELECT dataset_type FROM datasets WHERE dataset_id = ?",
        (SYNTHETIC_DEMO_DATASET_ID,),
    ).fetchone()
    if dataset is None:
        raise ValueError(
            f"Dataset {SYNTHETIC_DEMO_DATASET_ID!r} is not registered"
        )
    if dataset["dataset_type"] != "synthetic":
        raise RuntimeError(
            f"Dataset {SYNTHETIC_DEMO_DATASET_ID!r} is not a synthetic dataset"
        )

    leads = generate_synthetic_leads()
    placeholders = ", ".join("?" for _ in leads)
    existing_rows = connection.execute(
        f"""
        SELECT lead_id, dataset_id
        FROM leads
        WHERE lead_id IN ({placeholders})
        """,
        tuple(lead.lead_id for lead in leads),
    ).fetchall()
    conflicting_ids = [
        row["lead_id"]
        for row in existing_rows
        if row["dataset_id"] != SYNTHETIC_DEMO_DATASET_ID
    ]
    if conflicting_ids:
        raise RuntimeError(
            "Synthetic lead IDs are already used by another dataset: "
            + ", ".join(conflicting_ids)
        )

    cursor = connection.executemany(
        """
        INSERT INTO leads (
            lead_id, dataset_id, name, acquisition_source, campaign,
            created_at, stage, status, is_qualified, assigned_owner,
            last_activity_at, next_follow_up_at, converted_at, deal_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lead_id) DO NOTHING
        """,
        [
            (
                lead.lead_id,
                lead.dataset_id,
                lead.name,
                lead.acquisition_source.value,
                lead.campaign,
                lead.created_at,
                lead.stage.value,
                lead.status.value,
                int(lead.is_qualified),
                lead.assigned_owner,
                lead.last_activity_at,
                lead.next_follow_up_at,
                lead.converted_at,
                lead.deal_value,
            )
            for lead in leads
        ],
    )
    return cursor.rowcount


def _format_utc(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
