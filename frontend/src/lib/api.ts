import type {
  ActiveDatasetResponse,
  AnalyticsFilters,
  Dataset,
  DatasetListResponse,
  FunnelAnalytics,
  GrowthOverview,
  ImportHistoryItem,
  ImportPreview,
  ImportResult,
  Lead,
  LeadFilters,
  LeadListResponse,
  LeadWrite,
} from "../types";

const productionApiBaseUrl = "https://lead-conversion-intelligence.onrender.com";
const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.PROD ? productionApiBaseUrl : "")
).replace(/\/$/, "");

export const api = {
  getDatasets: (signal?: AbortSignal) =>
    getJson<DatasetListResponse>("/api/datasets", signal),
  getActiveDataset: (signal?: AbortSignal) =>
    getJson<ActiveDatasetResponse>("/api/datasets/active", signal),
  getGrowthOverview: (
    datasetId: string,
    filters: AnalyticsFilters = {},
    signal?: AbortSignal,
  ) =>
    getJson<GrowthOverview>(
      withQuery("/api/analytics/growth", { dataset_id: datasetId, ...filters }),
      signal,
    ),
  getFunnelAnalytics: (
    datasetId: string,
    filters: AnalyticsFilters = {},
    signal?: AbortSignal,
  ) =>
    getJson<FunnelAnalytics>(
      withQuery("/api/analytics/funnel", { dataset_id: datasetId, ...filters }),
      signal,
    ),
  getLeads: (datasetId: string, filters: LeadFilters, signal?: AbortSignal) => {
    const query = new URLSearchParams({ dataset_id: datasetId });
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return getJson<LeadListResponse>(`/api/leads?${query.toString()}`, signal);
  },
  getLead: (datasetId: string, leadId: string, signal?: AbortSignal) =>
    getJson<Lead>(
      `/api/leads/${encodeURIComponent(leadId)}?dataset_id=${encodeURIComponent(datasetId)}`,
      signal,
    ),
  createLead: (datasetId: string, lead: LeadWrite, adminToken: string) =>
    getJson<Lead>(`/api/leads?dataset_id=${encodeURIComponent(datasetId)}`, undefined, {
      method: "POST",
      headers: adminHeaders(adminToken),
      body: JSON.stringify(lead),
    }),
  updateLead: (
    datasetId: string,
    leadId: string,
    lead: LeadWrite,
    adminToken: string,
  ) =>
    getJson<Lead>(
      `/api/leads/${encodeURIComponent(leadId)}?dataset_id=${encodeURIComponent(datasetId)}`,
      undefined,
      {
        method: "PUT",
        headers: adminHeaders(adminToken),
        body: JSON.stringify(lead),
      },
    ),
  deleteLead: (datasetId: string, leadId: string, adminToken: string) =>
    deleteRequest(
      `/api/leads/${encodeURIComponent(leadId)}?dataset_id=${encodeURIComponent(datasetId)}`,
      adminToken,
    ),
  previewImport: (
    file: File,
    mapping?: Record<string, string>,
    datasetId?: string,
    signal?: AbortSignal,
  ) => {
    const body = new FormData();
    body.set("file", file);
    if (mapping) body.set("mapping", JSON.stringify(mapping));
    if (datasetId) body.set("dataset_id", datasetId);
    return getJson<ImportPreview>("/api/imports/preview", signal, {
      method: "POST",
      body,
    });
  },
  importCsv: (
    file: File,
    datasetName: string,
    adminToken: string,
    mapping?: Record<string, string>,
    datasetId?: string,
  ) => {
    const body = new FormData();
    body.set("file", file);
    body.set("dataset_name", datasetName);
    if (mapping) body.set("mapping", JSON.stringify(mapping));
    if (datasetId) body.set("dataset_id", datasetId);
    return getJson<ImportResult>("/api/datasets/import", undefined, {
      method: "POST",
      headers: adminTokenHeaders(adminToken),
      body,
    });
  },
  getImportHistory: (datasetId: string, signal?: AbortSignal) =>
    getJson<ImportHistoryItem[]>(
      `/api/imports?dataset_id=${encodeURIComponent(datasetId)}`,
      signal,
    ),
  renameDataset: (datasetId: string, name: string, adminToken: string) =>
    getJson<Dataset>(
      `/api/datasets/${encodeURIComponent(datasetId)}`,
      undefined,
      {
        method: "PATCH",
        headers: adminHeaders(adminToken),
        body: JSON.stringify({ name }),
      },
    ),
  deleteDataset: (datasetId: string, adminToken: string) =>
    deleteRequest(`/api/datasets/${encodeURIComponent(datasetId)}`, adminToken),
};

function withQuery(path: string, values: Record<string, string | boolean | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  return `${path}?${query.toString()}`;
}

function adminHeaders(token: string): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Admin-Token": token,
  };
}

function adminTokenHeaders(token: string): HeadersInit {
  return { Accept: "application/json", "X-Admin-Token": token };
}

async function deleteRequest(path: string, adminToken: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "DELETE",
    headers: { "X-Admin-Token": adminToken },
  });
  if (!response.ok) throw await responseError(response);
}

async function getJson<T>(
  path: string,
  signal?: AbortSignal,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Accept: "application/json", ...init?.headers },
    signal,
    ...init,
  });

  if (!response.ok) throw await responseError(response);
  return (await response.json()) as T;
}

async function responseError(response: Response): Promise<Error> {
  let message = `Request failed (${response.status})`;
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((item: unknown) => {
          if (
            typeof item !== "object" ||
            item === null ||
            !("msg" in item) ||
            typeof item.msg !== "string"
          ) {
            return [];
          }
          return [item.msg];
        });
        if (messages.length > 0) message = messages.join(" ");
      }
    }
  } catch {
    message = `Request failed (${response.status} ${response.statusText})`;
  }
  return new Error(message);
}
