import type {
  ActiveDatasetResponse,
  DatasetListResponse,
  FunnelAnalytics,
  GrowthOverview,
} from "../types";

const productionApiBaseUrl = "https://lead-conversion-intelligence.onrender.com";
const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.PROD ? productionApiBaseUrl : "")
).replace(/\/$/, "");

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      }
    } catch {
      message = `Request failed (${response.status} ${response.statusText})`;
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const api = {
  getDatasets: (signal?: AbortSignal) =>
    getJson<DatasetListResponse>("/api/datasets", signal),
  getActiveDataset: (signal?: AbortSignal) =>
    getJson<ActiveDatasetResponse>("/api/datasets/active", signal),
  getGrowthOverview: (datasetId: string, signal?: AbortSignal) =>
    getJson<GrowthOverview>(
      `/api/analytics/growth?dataset_id=${encodeURIComponent(datasetId)}`,
      signal,
    ),
  getFunnelAnalytics: (datasetId: string, signal?: AbortSignal) =>
    getJson<FunnelAnalytics>(
      `/api/analytics/funnel?dataset_id=${encodeURIComponent(datasetId)}`,
      signal,
    ),
};
