from dataclasses import dataclass
from enum import StrEnum


class DatasetType(StrEnum):
    SYNTHETIC = "synthetic"
    REAL = "real"


class LeadStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class LeadStatus(StrEnum):
    OPEN = "open"
    CONVERTED = "converted"
    LOST = "lost"


class AcquisitionSource(StrEnum):
    PAID_SEARCH = "paid_search"
    ORGANIC_SEARCH = "organic_search"
    REFERRAL = "referral"
    WEBINAR = "webinar"
    PARTNER = "partner"
    OUTBOUND = "outbound"


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    name: str
    dataset_type: DatasetType
    created_at: str
    lead_count: int = 0


@dataclass(frozen=True)
class Lead:
    lead_id: str
    dataset_id: str
    name: str
    acquisition_source: AcquisitionSource
    campaign: str
    created_at: str
    stage: LeadStage
    status: LeadStatus
    is_qualified: bool
    assigned_owner: str
    last_activity_at: str
    next_follow_up_at: str | None
    converted_at: str | None
    deal_value: float | None