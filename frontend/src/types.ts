export type LeadStage =
  | "new"
  | "contacted"
  | "qualified"
  | "proposal"
  | "negotiation"
  | "closed_won"
  | "closed_lost";

export interface Dataset {
  dataset_id: string;
  name: string;
  dataset_type: "synthetic" | "real";
  status: "active" | "inactive";
  created_at: string;
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
