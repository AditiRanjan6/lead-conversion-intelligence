import { useCallback, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Download,
  FileUp,
  LoaderCircle,
  Pencil,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { StatusPanel } from "../components/StatusPanel";
import { useAdminToken } from "../context/AdminTokenContext";
import { useApiResource } from "../hooks/useApiResource";
import { api } from "../lib/api";
import type { Dataset, ImportPreview } from "../types";
import { formatNumber } from "../utils/format";

interface DataManagementPageProps {
  datasets: Dataset[];
  selectedDatasetId: string;
  onDatasetChange: (datasetId: string) => void;
  onDatasetsChanged: (selectDatasetId?: string) => void;
}

const importFields = [
  ["name", "Lead name", true],
  ["acquisition_source", "Acquisition source", true],
  ["campaign", "Campaign", true],
  ["created_at", "Created at", true],
  ["stage", "Current stage", true],
  ["status", "Status", true],
  ["is_qualified", "Qualified", true],
  ["assigned_owner", "Assigned owner", true],
  ["last_activity_at", "Last activity at", true],
  ["lead_id", "Lead ID", false],
  ["next_follow_up_at", "Next follow-up at", false],
  ["converted_at", "Converted at", false],
  ["deal_value", "Deal value", false],
] as const;

export function DataManagementPage({
  datasets,
  selectedDatasetId,
  onDatasetChange,
  onDatasetsChanged,
}: DataManagementPageProps) {
  const { token, setToken } = useAdminToken();
  const [file, setFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [targetDatasetId, setTargetDatasetId] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [validatedMapping, setValidatedMapping] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const historyLoader = useCallback(
    (signal: AbortSignal) =>
      api.getImportHistory(selectedDatasetId, signal),
    [selectedDatasetId],
  );
  const history = useApiResource(historyLoader);
  const importedDatasets = useMemo(
    () => datasets.filter((dataset) => dataset.dataset_type === "real"),
    [datasets],
  );

  const resetImport = () => {
    setFile(null);
    setPreview(null);
    setMapping({});
    setValidatedMapping("");
    setMessage("");
    setError("");
  };

  const validateFile = async (
    selectedFile: File,
    nextMapping?: Record<string, string>,
    datasetId = targetDatasetId,
  ) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api.previewImport(
        selectedFile,
        nextMapping,
        datasetId || undefined,
      );
      setPreview(result);
      const useMapping = nextMapping ?? result.suggested_mapping;
      setMapping(useMapping);
      setValidatedMapping(JSON.stringify(useMapping));
    } catch (cause) {
      setPreview(null);
      setError(cause instanceof Error ? cause.message : "Unable to validate this CSV.");
    } finally {
      setBusy(false);
    }
  };

  const onFileSelected = (selectedFile: File | undefined) => {
    resetImport();
    if (!selectedFile) return;
    setFile(selectedFile);
    const basename = selectedFile.name.replace(/\.csv$/i, "");
    setDatasetName(basename);
    void validateFile(selectedFile);
  };

  const updateMapping = (target: string, source: string) => {
    setMapping((current) => {
      const next = { ...current };
      if (source) next[target] = source;
      else delete next[target];
      return next;
    });
  };

  const importRecords = async () => {
    if (!file || !preview || !token.trim()) {
      setError("Enter the admin token to enable the import.");
      return;
    }
    if (JSON.stringify(mapping) !== validatedMapping) {
      setError("Validate the preview again after changing column mappings.");
      return;
    }
    if (preview.valid_rows === 0) {
      setError("There are no valid, non-duplicate rows to import.");
      return;
    }
    const destination = targetDatasetId
      ? `append ${preview.valid_rows} valid lead(s) to the selected dataset`
      : `create “${datasetName.trim()}” with ${preview.valid_rows} valid lead(s)`;
    const skipped = preview.rejected_rows + preview.duplicate_rows;
    if (
      !window.confirm(
        `Confirm import: ${destination}. ${skipped} invalid or duplicate row(s) will be skipped. This cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api.importCsv(
        file,
        targetDatasetId ? "" : datasetName.trim(),
        token.trim(),
        mapping,
        targetDatasetId || undefined,
      );
      setMessage(
        `Imported ${formatNumber(result.imported_rows)} lead(s). ` +
          `${formatNumber(result.rejected_rows)} rejected and ` +
          `${formatNumber(result.duplicate_rows)} duplicate row(s) were skipped.`,
      );
      onDatasetsChanged(result.dataset_id);
      history.reload();
      resetImport();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The import failed.");
    } finally {
      setBusy(false);
    }
  };

  const rename = async (dataset: Dataset) => {
    if (!token.trim()) {
      setError("Enter the admin token before renaming a dataset.");
      return;
    }
    const nextName = window.prompt("Enter a new dataset name:", dataset.name);
    if (nextName === null || !nextName.trim()) return;
    setError("");
    try {
      await api.renameDataset(dataset.dataset_id, nextName.trim(), token.trim());
      setMessage(`Renamed dataset to “${nextName.trim()}”.`);
      onDatasetsChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to rename the dataset.");
    }
  };

  const removeDataset = async (dataset: Dataset) => {
    if (!token.trim()) {
      setError("Enter the admin token before deleting a dataset.");
      return;
    }
    const confirmed = window.confirm(
      `Delete “${dataset.name}” and all ${dataset.lead_count} lead record(s)? The built-in demo dataset is protected. This cannot be undone.`,
    );
    if (!confirmed) return;
    setError("");
    try {
      await api.deleteDataset(dataset.dataset_id, token.trim());
      if (dataset.dataset_id === selectedDatasetId) {
        onDatasetChange("synthetic-demo");
      }
      setMessage(`Deleted dataset “${dataset.name}”.`);
      onDatasetsChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete the dataset.");
    }
  };

  const downloadTemplate = () => {
    const header = importFields.map(([field]) => field).join(",");
    const example = [
      "",
      "Example lead only",
      "referral",
      "Example campaign",
      "2026-09-01T09:00:00Z",
      "new",
      "open",
      "false",
      "Example owner",
      "2026-09-01T09:00:00Z",
      "",
      "",
      "",
    ].join(",");
    const blob = new Blob([`${header}\r\n${example}\r\n`], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "lead-import-template.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const historyForSelected = history.data ?? [];

  return (
    <section className="page-content">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span /> DATA MANAGEMENT</div>
          <h1>Bring your data<br className="mobile-break" /> into focus.</h1>
          <p className="page-intro">
            Import real lead records, manage datasets, and inspect import history.
          </p>
        </div>
        <button className="button button-secondary" onClick={downloadTemplate}>
          <Download size={16} /> Download CSV template
        </button>
      </div>

      <section className="content-card admin-token-card">
        <div className="admin-token-icon"><ShieldCheck size={18} /></div>
        <div className="admin-token-copy">
          <strong>Admin access for data changes</strong>
          <span>
            Token stays in this tab’s memory and is sent only with protected write requests.
          </span>
        </div>
        <label className="admin-token-input">
          <span className="sr-only">Admin token</span>
          <input
            aria-label="Admin token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Enter server admin token"
          />
        </label>
      </section>

      {error && <div className="inline-alert inline-alert-error" role="alert"><AlertCircle size={17} />{error}</div>}
      {message && <div className="inline-alert inline-alert-success" role="status"><Check size={17} />{message}</div>}

      <section className="content-card import-card">
        <div className="card-heading">
          <div>
            <span className="card-kicker">CSV IMPORT</span>
            <h2>Preview before importing</h2>
            <p>UTF-8 CSV · up to 5 MB and 10,000 rows. Existing data is never overwritten.</p>
          </div>
        </div>

        <div className="import-form-grid">
          <label className="field-label">
            Import into
            <select
              value={targetDatasetId}
              onChange={(event) => {
                const datasetId = event.target.value;
                setTargetDatasetId(datasetId);
                if (file) {
                  setPreview(null);
                  setMessage("");
                  void validateFile(file, undefined, datasetId);
                }
              }}
            >
              <option value="">Create a new dataset</option>
              {importedDatasets.map((dataset) => (
                <option key={dataset.dataset_id} value={dataset.dataset_id}>
                  {dataset.name} ({dataset.lead_count} leads)
                </option>
              ))}
            </select>
          </label>
          {!targetDatasetId && (
            <label className="field-label">
              New dataset name
              <input
                maxLength={120}
                value={datasetName}
                onChange={(event) => setDatasetName(event.target.value)}
                placeholder="For example: Q3 inbound leads"
              />
            </label>
          )}
        </div>

        <label className="upload-dropzone">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              onFileSelected(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <span className="upload-dropzone-icon"><FileUp size={20} /></span>
          <strong>{file?.name ?? "Choose a CSV file"}</strong>
          <span>{file ? `${(file.size / 1024).toFixed(1)} KB` : "File stays in memory during preview; nothing is stored until you import."}</span>
        </label>

        {busy && <p className="inline-progress"><LoaderCircle className="status-icon-spin" size={17} /> Validating CSV…</p>}

        {preview && (
          <>
            <div className="import-summary-grid" aria-label="Import validation summary">
              <div><span>Total rows</span><strong>{formatNumber(preview.total_rows)}</strong></div>
              <div><span>Valid</span><strong>{formatNumber(preview.valid_rows)}</strong></div>
              <div><span>Rejected</span><strong>{formatNumber(preview.rejected_rows)}</strong></div>
              <div><span>Duplicates</span><strong>{formatNumber(preview.duplicate_rows)}</strong></div>
            </div>
            <div className="mapping-panel">
              <div>
                <span className="card-kicker">COLUMN MAPPING</span>
                <h3>Match your CSV columns</h3>
                <p>Required fields are marked. Unmapped optional columns are left blank.</p>
              </div>
              <div className="mapping-grid">
                {importFields.map(([field, label, required]) => (
                  <label className="field-label" key={field}>
                    {label}{required ? " *" : ""}
                    <select
                      value={mapping[field] ?? ""}
                      onChange={(event) => updateMapping(field, event.target.value)}
                    >
                      <option value="">Not mapped</option>
                      {preview.headers.map((header) => (
                        <option key={`${field}-${header}`} value={header}>{header}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </div>
            {JSON.stringify(mapping) !== validatedMapping && (
              <button
                className="button button-secondary"
                onClick={() => file && void validateFile(file, mapping)}
                disabled={busy}
              >
                <RefreshCw size={15} /> Revalidate mapping
              </button>
            )}
            {preview.sample_rows.length > 0 && (
              <div className="table-scroll import-sample">
                <table>
                  <thead><tr><th>CSV row</th><th>Lead</th><th>Source</th><th>Stage</th><th>Status</th><th>Created</th></tr></thead>
                  <tbody>
                    {preview.sample_rows.map((row) => (
                      <tr key={String(row.row_number)}>
                        <td>{String(row.row_number)}</td>
                        <td>{String(row.name)}</td>
                        <td>{String(row.acquisition_source)}</td>
                        <td>{String(row.stage)}</td>
                        <td>{String(row.status)}</td>
                        <td>{String(row.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="table-caption">Showing up to 20 valid rows. Invalid and duplicate rows are listed below.</p>
              </div>
            )}
            {preview.errors.length > 0 && (
              <div className="validation-errors">
                <strong>Rows requiring attention</strong>
                <ul>
                  {preview.errors.slice(0, 20).map((item) => (
                    <li key={item.row_number}>Row {item.row_number}: {item.messages.join(" ")}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="import-actions">
              <button className="button button-secondary" onClick={resetImport} disabled={busy}>
                Cancel preview
              </button>
              <button
                className="button button-primary"
                onClick={() => void importRecords()}
                disabled={busy || !file || preview.valid_rows === 0 || !token.trim() || (!targetDatasetId && !datasetName.trim()) || JSON.stringify(mapping) !== validatedMapping}
              >
                <FileUp size={16} /> Import {formatNumber(preview.valid_rows)} valid rows
              </button>
            </div>
          </>
        )}
      </section>

      <section className="content-card datasets-card">
        <div className="card-heading">
          <div>
            <span className="card-kicker">DATASETS</span>
            <h2>Available data</h2>
            <p>Every chart and lead request is scoped to one selected dataset.</p>
          </div>
          <button className="icon-button" aria-label="Refresh datasets" onClick={() => onDatasetsChanged()}><RefreshCw size={16} /></button>
        </div>
        <div className="dataset-management-list">
          {datasets.map((dataset) => (
            <article className="dataset-management-row" key={dataset.dataset_id}>
              <div className="dataset-row-mark">{dataset.dataset_type === "synthetic" ? "D" : "I"}</div>
              <div className="dataset-row-copy">
                <strong>{dataset.name}</strong>
                <span>{dataset.dataset_type === "synthetic" ? "Synthetic demo" : "Imported dataset"} · {formatNumber(dataset.lead_count)} leads · {dataset.dataset_id}</span>
              </div>
              {dataset.dataset_id === selectedDatasetId && <span className="dataset-selected-badge">Current</span>}
              <button
                className="button button-small button-secondary"
                onClick={() => onDatasetChange(dataset.dataset_id)}
                disabled={dataset.dataset_id === selectedDatasetId}
              >
                Use dataset
              </button>
              {dataset.dataset_type === "real" && (
                <>
                  <button className="icon-button" aria-label={`Rename ${dataset.name}`} onClick={() => void rename(dataset)}><Pencil size={15} /></button>
                  <button className="icon-button icon-button-danger" aria-label={`Delete ${dataset.name}`} onClick={() => void removeDataset(dataset)}><Trash2 size={15} /></button>
                </>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="content-card history-card">
        <div className="card-heading">
          <div>
            <span className="card-kicker">IMPORT HISTORY</span>
            <h2>{datasets.find((dataset) => dataset.dataset_id === selectedDatasetId)?.name ?? "Selected dataset"}</h2>
          </div>
          <Link className="text-link" to="/leads">Open lead explorer</Link>
        </div>
        {history.loading ? (
          <p className="inline-progress"><LoaderCircle className="status-icon-spin" size={17} /> Loading history…</p>
        ) : history.error ? (
          <StatusPanel error={history.error} onRetry={history.reload} />
        ) : historyForSelected.length === 0 ? (
          <p className="empty-inline">No CSV imports are recorded for this dataset.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Filename</th><th>Imported</th><th>Rows imported</th><th>Skipped</th><th>Outcome</th></tr></thead>
              <tbody>
                {historyForSelected.map((item) => (
                  <tr key={item.import_id}>
                    <td>{item.filename}</td>
                    <td>{item.imported_at}</td>
                    <td>{formatNumber(item.imported_rows)} / {formatNumber(item.total_rows)}</td>
                    <td>{formatNumber(item.rejected_rows + item.duplicate_rows)}</td>
                    <td>{item.outcome === "completed" ? "Complete" : "Completed with skipped rows"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
