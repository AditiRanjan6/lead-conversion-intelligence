export type LeadStage =
  | "new"
  | "contacted"
  | "qualified"
  | "proposal"
  | "negotiation"
  | "closed_won"
  | "closed_lost";

export type LeadStatus = "open" | "converted" | "lost";
export type AcquisitionSource =
  | "paid_search"
  | "organic_search"
  | "referral"
  | "webinar"
  | "partner"
  | "outbound";

export interface AnalyticsFilters {
  stage?: LeadStage;
  status?: LeadStatus;
  source?: AcquisitionSource;
  qualified?: boolean;
  date_from?: string;
  date_to?: string;
}

export interface Dataset {
  dataset_id: string;
  name: string;
  dataset_type: "synthetic" | "real";
  status: "active" | "inactive";
  created_at: string;
  lead_count: number;
}

export interface DatasetListResponse {
  datasets: Dataset[];
}

export interface ActiveDatasetResponse {
  active_dataset: Dataset | null;
}

export interface GrowthOverview {
  total_leads: number;
  qualified_leads: number;
  converted_leads: number;
  lost_leads: number;
  conversion_rate: number;
  qualification_rate: number;
  converted_deal_value: number;
}

export interface StageMetric {
  stage: LeadStage;
  lead_count: number;
  percentage_of_total: number;
}

export interface LostStageMetric {
  stage: LeadStage;
  lead_count: number;
  percentage_of_lost_leads: number;
}

export interface FunnelAnalytics {
  dataset_id: string;
  total_leads: number;
  stage_distribution: StageMetric[];
  funnel: StageMetric[];
  loss_analysis: {
    total_lost_leads: number;
    loss_rate: number;
    leads_by_stage: LostStageMetric[];
  };
  data_limitations: string[];
}

export interface Lead {
  lead_id: string;
  dataset_id: string;
  name: string;
  acquisition_source: AcquisitionSource;
  campaign: string;
  created_at: string;
  stage: LeadStage;
  status: LeadStatus;
  is_qualified: boolean;
  assigned_owner: string;
  last_activity_at: string;
  next_follow_up_at: string | null;
  converted_at: string | null;
  deal_value: number | null;
}

export type LeadWrite = Omit<Lead, "dataset_id" | "lead_id"> & {
  lead_id?: string;
};

export interface LeadListResponse {
  leads: Lead[];
  total: number;
  page: number;
  page_size: number;
  filter_options: Record<string, string[]>;
}

export interface LeadFilters {
  search?: string;
  stage?: LeadStage;
  status?: LeadStatus;
  qualified?: boolean;
  source?: AcquisitionSource;
  owner?: string;
  campaign?: string;
  date_from?: string;
  date_to?: string;
  sort?: string;
  direction?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface ImportPreview {
  headers: string[];
  suggested_mapping: Record<string, string>;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  errors: Array<{ row_number: number; messages: string[] }>;
  sample_rows: Array<Record<string, unknown>>;
}

export interface ImportResult {
  dataset_id: string;
  import_id: string;
  imported_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  outcome: string;
}

export interface ImportHistoryItem {
  import_id: string;
  dataset_id: string;
  filename: string;
  imported_at: string;
  total_rows: number;
  imported_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  outcome: string;
}
