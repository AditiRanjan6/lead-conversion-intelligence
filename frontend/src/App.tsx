import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { StatusPanel } from "./components/StatusPanel";
import { AdminTokenProvider } from "./context/AdminTokenContext";
import { AnalyticsFilterProvider } from "./context/AnalyticsFilterContext";
import { useApiResource } from "./hooks/useApiResource";
import { api } from "./lib/api";
import type { ActiveDatasetResponse, DatasetListResponse } from "./types";
import "./styles.css";

const GrowthOverviewPage = lazy(() =>
  import("./pages/GrowthOverviewPage").then((module) => ({
    default: module.GrowthOverviewPage,
  })),
);
const FunnelIntelligencePage = lazy(() =>
  import("./pages/FunnelIntelligencePage").then((module) => ({
    default: module.FunnelIntelligencePage,
  })),
);
const DataManagementPage = lazy(() =>
  import("./pages/DataManagementPage").then((module) => ({
    default: module.DataManagementPage,
  })),
);
const LeadExplorerPage = lazy(() =>
  import("./pages/LeadExplorerPage").then((module) => ({
    default: module.LeadExplorerPage,
  })),
);

interface DatasetBootstrap {
  registry: DatasetListResponse;
  active: ActiveDatasetResponse;
}

function Workspace() {
  const loader = useCallback(async (signal: AbortSignal): Promise<DatasetBootstrap> => {
    const [registry, active] = await Promise.all([
      api.getDatasets(signal),
      api.getActiveDataset(signal),
    ]);
    return { registry, active };
  }, []);
  const datasetsResource = useApiResource(loader);
  const pendingDatasetId = useRef<string | null>(null);
  const datasets = useMemo(
    () => datasetsResource.data?.registry.datasets ?? [],
    [datasetsResource.data],
  );
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const initialDatasetId =
    datasetsResource.data?.active.active_dataset?.dataset_id ??
    datasets[0]?.dataset_id ??
    "";
  const effectiveDatasetId = selectedDatasetId || initialDatasetId;

  useEffect(() => {
    if (!datasetsResource.data) return;
    const { active, registry } = datasetsResource.data;
    const preferred = active.active_dataset?.dataset_id ?? registry.datasets[0]?.dataset_id ?? "";
    const pending = pendingDatasetId.current;
    if (pending && registry.datasets.some((dataset) => dataset.dataset_id === pending)) {
      pendingDatasetId.current = null;
      setSelectedDatasetId(pending);
      return;
    }
    pendingDatasetId.current = null;
    setSelectedDatasetId((current) =>
      registry.datasets.some((dataset) => dataset.dataset_id === current)
        ? current
        : preferred,
    );
  }, [datasetsResource.data]);
  const refreshDatasets = useCallback(
    (selectDatasetId?: string) => {
      pendingDatasetId.current = selectDatasetId ?? null;
      datasetsResource.reload();
    },
    [datasetsResource.reload],
  );

  if (datasetsResource.loading) {
    return (
      <main className="bootstrap-state">
        <LoaderCircle className="status-icon status-icon-spin" size={24} />
        <strong>Connecting to your workspace</strong>
        <span>Loading registered datasets from the API.</span>
      </main>
    );
  }

  if (datasetsResource.error) {
    return (
      <main className="bootstrap-state bootstrap-state-error" role="alert">
        <AlertCircle size={24} />
        <strong>Couldn’t connect to the analytics API</strong>
        <span>{datasetsResource.error}</span>
        <button
          className="button button-secondary status-retry"
          onClick={datasetsResource.reload}
        >
          <RefreshCw size={15} />
          Try again
        </button>
      </main>
    );
  }

  if (datasets.length === 0) {
    return (
      <main className="bootstrap-state">
        <StatusPanel
          empty
          emptyTitle="No registered datasets"
          emptyMessage="Register a dataset in the API before opening analytics."
        />
      </main>
    );
  }

  return (
    <AppLayout
      datasets={datasets}
      selectedDatasetId={effectiveDatasetId}
      onDatasetChange={setSelectedDatasetId}
      datasetLoading={datasetsResource.loading}
    >
      <Suspense
        fallback={
          <div className="page-loading" role="status">
            <LoaderCircle className="status-icon status-icon-spin" size={22} />
            <span>Opening analytics…</span>
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<GrowthOverviewPage datasetId={effectiveDatasetId} />} />
          <Route
            path="/funnel"
            element={<FunnelIntelligencePage datasetId={effectiveDatasetId} />}
          />
          <Route
            path="/data"
            element={
              <DataManagementPage
                datasets={datasets}
                selectedDatasetId={effectiveDatasetId}
                onDatasetChange={setSelectedDatasetId}
                onDatasetsChanged={refreshDatasets}
              />
            }
          />
          <Route
            path="/leads"
            element={<LeadExplorerPage datasetId={effectiveDatasetId} />}
          />
          <Route path="*" element={<GrowthOverviewPage datasetId={effectiveDatasetId} />} />
        </Routes>
      </Suspense>
    </AppLayout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AdminTokenProvider>
        <AnalyticsFilterProvider>
          <Workspace />
        </AnalyticsFilterProvider>
      </AdminTokenProvider>
    </BrowserRouter>
  );
}
