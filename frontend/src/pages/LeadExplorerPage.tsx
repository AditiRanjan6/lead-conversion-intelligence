import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { StatusPanel } from "../components/StatusPanel";
import { useAdminToken } from "../context/AdminTokenContext";
import { useAnalyticsFilters } from "../context/AnalyticsFilterContext";
import { AnalyticsFilterBar } from "../components/AnalyticsFilterBar";
import { useApiResource } from "../hooks/useApiResource";
import { api } from "../lib/api";
import type {
  AcquisitionSource,
  Lead,
  LeadFilters,
  LeadStage,
  LeadStatus,
  LeadWrite,
} from "../types";
import { formatNumber, formatStage } from "../utils/format";
import { escapeCsvCell } from "../utils/csv";

const sources: AcquisitionSource[] = [
  "paid_search",
  "organic_search",
  "referral",
  "webinar",
  "partner",
  "outbound",
];
const stages: LeadStage[] = [
  "new",
  "contacted",
  "qualified",
  "proposal",
  "negotiation",
  "closed_won",
  "closed_lost",
];
const statuses: LeadStatus[] = ["open", "converted", "lost"];
const pageSize = 25;

function dateValue(value?: string | null): string {
  return value?.slice(0, 10) ?? "";
}

function timestampValue(value: string): string {
  return value ? `${value}T12:00:00Z` : "";
}

function blankLead(): LeadWrite {
  const today = new Date().toISOString().slice(0, 10);
  return {
    name: "",
    acquisition_source: "referral",
    campaign: "",
    created_at: timestampValue(today),
    stage: "new",
    status: "open",
    is_qualified: false,
    assigned_owner: "",
    last_activity_at: timestampValue(today),
    next_follow_up_at: null,
    converted_at: null,
    deal_value: null,
  };
}

function editableLead(lead: Lead): LeadWrite {
  return {
    ...lead,
    created_at: lead.created_at,
    lead_id: lead.lead_id,
  };
}

export function LeadExplorerPage({ datasetId }: { datasetId: string }) {
  const { token, setToken } = useAdminToken();
  const { filters: analyticsFilters } = useAnalyticsFilters();
  const [searchParams] = useSearchParams();
  const initialStage = searchParams.get("stage");
  const initialStatus = searchParams.get("status");
  const initialQualified = searchParams.get("qualified");
  const [filters, setFilters] = useState<LeadFilters>(() => ({
    stage: stages.includes(initialStage as LeadStage)
      ? (initialStage as LeadStage)
      : undefined,
    status: statuses.includes(initialStatus as LeadStatus)
      ? (initialStatus as LeadStatus)
      : undefined,
    qualified:
      initialQualified === "true"
        ? true
        : initialQualified === "false"
          ? false
          : undefined,
    page: 1,
    page_size: pageSize,
    sort: "created_at",
    direction: "desc",
  }));
  const [draft, setDraft] = useState<LeadFilters>(filters);
  const [editing, setEditing] = useState<LeadWrite | null>(null);
  const [details, setDetails] = useState<Lead | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const loader = useCallback(
    (signal: AbortSignal) =>
      api.getLeads(datasetId, { ...analyticsFilters, ...filters }, signal),
    [datasetId, filters, analyticsFilters],
  );
  const resource = useApiResource(loader);
  const totalPages = Math.max(1, Math.ceil((resource.data?.total ?? 0) / pageSize));
  const activeFilterCount = useMemo(
    () =>
      [
        filters.search,
        filters.stage,
        filters.status,
        filters.qualified,
        filters.source,
        filters.owner,
        filters.campaign,
        filters.date_from,
        filters.date_to,
        analyticsFilters.stage,
        analyticsFilters.status,
        analyticsFilters.qualified,
        analyticsFilters.source,
        analyticsFilters.date_from,
        analyticsFilters.date_to,
      ].filter((value) => value !== undefined && value !== "").length,
    [analyticsFilters, filters],
  );

  useEffect(() => {
    setFilters((current) => ({ ...current, page: 1 }));
  }, [datasetId]);

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft.date_from && draft.date_to && draft.date_from > draft.date_to) {
      setError("The start date must be on or before the end date.");
      return;
    }
    setError("");
    setFilters({ ...draft, page: 1, page_size: pageSize });
  };

  const resetFilters = () => {
    const cleared: LeadFilters = {
      page: 1,
      page_size: pageSize,
      sort: "created_at",
      direction: "desc",
    };
    setDraft(cleared);
    setFilters(cleared);
    setError("");
  };

  const setPage = (page: number) => {
    setFilters((current) => ({ ...current, page }));
  };

  const setSort = (column: string) => {
    setFilters((current) => ({
      ...current,
      page: 1,
      sort: column,
      direction:
        current.sort === column && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  const persistLead = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    if (!token.trim()) {
      setError("Enter the admin token to create or edit leads.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        ...editing,
        name: editing.name.trim(),
        campaign: editing.campaign.trim(),
        assigned_owner: editing.assigned_owner.trim(),
        next_follow_up_at: editing.next_follow_up_at || null,
        converted_at: editing.converted_at || null,
        deal_value: editing.deal_value === null ? null : Number(editing.deal_value),
      };
      const saved = editing.lead_id
        ? await api.updateLead(datasetId, editing.lead_id, payload, token.trim())
        : await api.createLead(datasetId, payload, token.trim());
      setEditing(null);
      setNotice(`Saved lead “${saved.name}”.`);
      resource.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save this lead.");
    } finally {
      setSaving(false);
    }
  };

  const removeLead = async (lead: Lead) => {
    if (!token.trim()) {
      setError("Enter the admin token before deleting a lead.");
      return;
    }
    if (!window.confirm(`Delete lead “${lead.name}”? This cannot be undone.`)) return;
    setError("");
    setNotice("");
    try {
      await api.deleteLead(datasetId, lead.lead_id, token.trim());
      setNotice(`Deleted lead “${lead.name}”.`);
      setDetails(null);
      resource.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete this lead.");
    }
  };

  const exportCsv = async () => {
    if (!resource.data) return;
    const total = resource.data.total;
    if (total > 1_000 && !window.confirm(`Export all ${formatNumber(total)} filtered leads?`)) {
      return;
    }
    if (total > 50_000) {
      setError("Exports are limited to 50,000 filtered records.");
      return;
    }
    setError("");
    try {
      const exportPageSize = 100;
      const exportPageCount = Math.max(1, Math.ceil(total / exportPageSize));
      const exportFilters = { ...filters, page_size: exportPageSize };
      const firstPage = await api.getLeads(datasetId, {
        ...exportFilters,
        page: 1,
      });
      const pages: Lead[][] = [firstPage.leads];
      for (let first = 2; first <= exportPageCount; first += 10) {
        const batch = await Promise.all(
          Array.from(
            { length: Math.min(10, exportPageCount - first + 1) },
            (_, offset) =>
              api.getLeads(datasetId, { ...exportFilters, page: first + offset }),
          ),
        );
        pages.push(...batch.map((pageResult) => pageResult.leads));
      }
      const columns: Array<keyof Lead> = [
        "lead_id",
        "name",
        "acquisition_source",
        "campaign",
        "created_at",
        "stage",
        "status",
        "is_qualified",
        "assigned_owner",
        "last_activity_at",
        "next_follow_up_at",
        "converted_at",
        "deal_value",
      ];
      const rows = pages.flat();
      if (rows.length !== total) {
        throw new Error("The filtered lead count changed during export; retry the export.");
      }
      const csv = [
        columns.map(escapeCsvCell).join(","),
        ...rows.map((lead) => columns.map((column) => escapeCsvCell(lead[column])).join(",")),
      ].join("\r\n");
      const blob = new Blob([`\uFEFF${csv}\r\n`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `leads-${datasetId}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(`Exported ${formatNumber(rows.length)} filtered lead(s).`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to export filtered leads.");
    }
  };

  const availableOptions = resource.data?.filter_options;

  return (
    <section className="page-content">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span /> LEAD EXPLORER</div>
          <h1>Every lead,<br className="mobile-break" /> easy to inspect.</h1>
          <p className="page-intro">Search, filter, review, and manage records in the selected dataset.</p>
        </div>
        <div className="lead-heading-actions">
          <button className="button button-secondary" onClick={() => void exportCsv()} disabled={!resource.data || resource.loading}>
            <Download size={16} /> Export filtered CSV
          </button>
          <button className="button button-primary" onClick={() => setEditing(blankLead())}>
            <Plus size={16} /> Add lead
          </button>
        </div>
      </div>

      <AnalyticsFilterBar />

      <section className="content-card admin-token-card">
        <div className="admin-token-copy">
          <strong>Admin access for record changes</strong>
          <span>Required by the backend for create, edit, and delete. Kept only in this tab’s memory.</span>
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
      {notice && <div className="inline-alert inline-alert-success" role="status">{notice}</div>}

      <form className="content-card lead-filter-card" onSubmit={applyFilters}>
        <div className="filter-card-heading">
          <div>
            <span className="card-kicker">NARROW RESULTS</span>
            <h2>Find a lead</h2>
            <p>These search, owner, and campaign filters refine the shared selection above.</p>
          </div>
          <button className="button button-text" type="button" onClick={resetFilters}>Reset filters</button>
        </div>
        <div className="lead-filter-grid">
          <label className="field-label search-field">
            Search leads
            <span className="search-input-wrap"><Search size={16} /><input value={draft.search ?? ""} onChange={(event) => setDraft({ ...draft, search: event.target.value })} placeholder="Name, campaign, owner, ID" /></span>
          </label>
          <label className="field-label">Owner
            <select value={draft.owner ?? ""} onChange={(event) => setDraft({ ...draft, owner: event.target.value || undefined })}>
              <option value="">All owners</option>{(availableOptions?.owner ?? []).map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label className="field-label">Campaign
            <select value={draft.campaign ?? ""} onChange={(event) => setDraft({ ...draft, campaign: event.target.value || undefined })}>
              <option value="">All campaigns</option>{(availableOptions?.campaign ?? []).map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <button className="button button-primary filter-submit" type="submit">Apply filters{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ""}</button>
        </div>
      </form>

      <section className="content-card leads-table-card">
        <div className="card-heading">
          <div><span className="card-kicker">LEAD RECORDS</span><h2>{resource.data ? `${formatNumber(resource.data.total)} results` : "Dataset records"}</h2></div>
          <button className="icon-button" aria-label="Refresh leads" onClick={resource.reload}><RefreshCw size={16} /></button>
        </div>
        {resource.loading || resource.error || (resource.data?.total ?? 0) === 0 ? (
          <StatusPanel
            loading={resource.loading}
            error={resource.error}
            onRetry={resource.reload}
            empty={Boolean(resource.data && resource.data.total === 0 && !resource.loading && !resource.error)}
            emptyTitle={activeFilterCount ? "No leads match these filters" : "No leads in this dataset"}
            emptyMessage={activeFilterCount ? "Adjust or reset filters to see more records." : "Import CSV data to add records to this dataset."}
          />
        ) : (
          <>
            <div className="table-scroll">
              <table className="leads-table">
                <thead>
                  <tr>
                    <th><button className="table-sort" onClick={() => setSort("name")}>Lead name</button></th>
                    <th><button className="table-sort" onClick={() => setSort("stage")}>Current stage</button></th>
                    <th><button className="table-sort" onClick={() => setSort("status")}>Status</button></th>
                    <th><button className="table-sort" onClick={() => setSort("source")}>Source</button></th>
                    <th><button className="table-sort" onClick={() => setSort("owner")}>Owner</button></th>
                    <th><button className="table-sort" onClick={() => setSort("campaign")}>Campaign</button></th>
                    <th><button className="table-sort" onClick={() => setSort("created_at")}>Created</button></th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {resource.data?.leads.map((lead) => (
                    <tr key={lead.lead_id}>
                      <td><button className="lead-name-link" onClick={() => setDetails(lead)}>{lead.name}</button></td>
                      <td>{formatStage(lead.stage)}</td>
                      <td><span className={`status-chip status-chip-${lead.status}`}>{lead.status}</span></td>
                      <td>{formatStage(lead.acquisition_source)}</td>
                      <td>{lead.assigned_owner}</td>
                      <td>{lead.campaign}</td>
                      <td>{dateValue(lead.created_at)}</td>
                      <td>
                        <div className="lead-row-actions">
                          <button className="button button-small button-secondary" onClick={() => setEditing(editableLead(lead))}>Edit</button>
                          <button className="icon-button icon-button-danger" aria-label={`Delete ${lead.name}`} onClick={() => void removeLead(lead)}><Trash2 size={15} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination-bar">
              <span>Page {resource.data?.page ?? 1} of {totalPages} · {formatNumber(resource.data?.total ?? 0)} leads</span>
              <div>
                <button className="icon-button" aria-label="Previous page" disabled={filters.page === 1} onClick={() => setPage(Math.max(1, (filters.page ?? 1) - 1))}><ChevronLeft size={17} /></button>
                <button className="icon-button" aria-label="Next page" disabled={(filters.page ?? 1) >= totalPages} onClick={() => setPage(Math.min(totalPages, (filters.page ?? 1) + 1))}><ChevronRight size={17} /></button>
              </div>
            </div>
          </>
        )}
      </section>

      {editing && (
        <LeadEditor
          initial={editing}
          saving={saving}
          onClose={() => setEditing(null)}
          onChange={setEditing}
          onSubmit={persistLead}
        />
      )}
      {details && (
        <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDetails(null)}>
          <section className="content-card lead-details-modal" role="dialog" aria-modal="true" aria-labelledby="lead-details-title">
            <div className="modal-heading"><div><span className="card-kicker">LEAD DETAILS</span><h2 id="lead-details-title">{details.name}</h2></div><button className="icon-button" aria-label="Close details" onClick={() => setDetails(null)}><X size={18} /></button></div>
            <dl className="lead-details-grid">
              <dt>Record ID</dt><dd>{details.lead_id}</dd><dt>Dataset</dt><dd>{details.dataset_id}</dd>
              <dt>Current stage</dt><dd>{formatStage(details.stage)}</dd><dt>Status</dt><dd>{details.status}</dd>
              <dt>Qualified</dt><dd>{details.is_qualified ? "Yes" : "No"}</dd><dt>Source</dt><dd>{formatStage(details.acquisition_source)}</dd>
              <dt>Campaign</dt><dd>{details.campaign}</dd><dt>Owner</dt><dd>{details.assigned_owner}</dd>
              <dt>Created</dt><dd>{details.created_at}</dd><dt>Last activity</dt><dd>{details.last_activity_at}</dd>
              <dt>Next follow-up</dt><dd>{details.next_follow_up_at ?? "Not scheduled"}</dd>
              <dt>Converted</dt><dd>{details.converted_at ?? "Not converted"}</dd>
              <dt>Deal value</dt><dd>{details.deal_value ?? "Not recorded"}</dd>
            </dl>
            <Link className="text-link" to="/data">Manage source dataset</Link>
          </section>
        </div>
      )}
    </section>
  );
}

function LeadEditor({
  initial,
  saving,
  onClose,
  onChange,
  onSubmit,
}: {
  initial: LeadWrite;
  saving: boolean;
  onClose: () => void;
  onChange: (value: LeadWrite) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const createdDate = dateValue(initial.created_at);
  const update = <K extends keyof LeadWrite>(key: K, value: LeadWrite[K]) =>
    onChange({ ...initial, [key]: value });
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <form className="content-card lead-editor-modal" role="dialog" aria-modal="true" aria-labelledby="lead-editor-title" onSubmit={onSubmit}>
        <div className="modal-heading"><div><span className="card-kicker">{initial.lead_id ? "EDIT RECORD" : "NEW RECORD"}</span><h2 id="lead-editor-title">{initial.lead_id ? "Update lead" : "Add a lead"}</h2></div><button className="icon-button" type="button" aria-label="Close editor" onClick={onClose}><X size={18} /></button></div>
        <div className="lead-editor-grid">
          <label className="field-label">Lead name<input required maxLength={200} value={initial.name} onChange={(event) => update("name", event.target.value)} /></label>
          <label className="field-label">Source<select value={initial.acquisition_source} onChange={(event) => update("acquisition_source", event.target.value as AcquisitionSource)}>{sources.map((source) => <option key={source} value={source}>{formatStage(source)}</option>)}</select></label>
          <label className="field-label">Campaign<input required maxLength={200} value={initial.campaign} onChange={(event) => update("campaign", event.target.value)} /></label>
          <label className="field-label">Owner<input required maxLength={120} value={initial.assigned_owner} onChange={(event) => update("assigned_owner", event.target.value)} /></label>
          <label className="field-label">Created date<input required type="date" value={createdDate} onChange={(event) => update("created_at", timestampValue(event.target.value))} /></label>
          <label className="field-label">Current stage<select value={initial.stage} onChange={(event) => update("stage", event.target.value as LeadStage)}>{stages.map((stage) => <option key={stage} value={stage}>{formatStage(stage)}</option>)}</select></label>
          <label className="field-label">Status<select value={initial.status} onChange={(event) => {
            const status = event.target.value as LeadStatus;
            const stage = status === "converted" ? "closed_won" : status === "lost" ? "closed_lost" : initial.stage === "closed_won" || initial.stage === "closed_lost" ? "new" : initial.stage;
            onChange({
              ...initial,
              status,
              stage,
              next_follow_up_at: status === "open" ? initial.next_follow_up_at : null,
              converted_at: status === "converted" ? (initial.converted_at ?? timestampValue(createdDate)) : null,
              deal_value: status === "converted" ? (initial.deal_value ?? 1) : null,
            });
          }}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
          <label className="field-label">Last activity<input required type="date" value={dateValue(initial.last_activity_at)} onChange={(event) => update("last_activity_at", timestampValue(event.target.value))} /></label>
          <label className="field-label checkbox-field"><input type="checkbox" checked={initial.is_qualified} onChange={(event) => update("is_qualified", event.target.checked)} /> Qualified</label>
          {initial.status === "open" && <label className="field-label">Next follow-up<input type="date" value={dateValue(initial.next_follow_up_at)} onChange={(event) => update("next_follow_up_at", event.target.value ? timestampValue(event.target.value) : null)} /></label>}
          {initial.status === "converted" && <>
            <label className="field-label">Converted date<input required type="date" value={dateValue(initial.converted_at)} onChange={(event) => update("converted_at", timestampValue(event.target.value))} /></label>
            <label className="field-label">Deal value<input required min="0.01" step="0.01" type="number" value={initial.deal_value ?? ""} onChange={(event) => update("deal_value", event.target.value ? Number(event.target.value) : null)} /></label>
          </>}
        </div>
        <div className="modal-actions"><button className="button button-secondary" type="button" onClick={onClose}>Cancel</button><button className="button button-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle className="status-icon-spin" size={16} /> : null}Save lead</button></div>
      </form>
    </div>
  );
}
