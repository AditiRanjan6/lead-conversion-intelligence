import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { RotateCcw, SlidersHorizontal } from "lucide-react";
import { useAnalyticsFilters } from "../context/AnalyticsFilterContext";
import type {
  AcquisitionSource,
  AnalyticsFilters,
  LeadStage,
  LeadStatus,
} from "../types";
import { formatStage } from "../utils/format";

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
const sources: AcquisitionSource[] = [
  "paid_search",
  "organic_search",
  "referral",
  "webinar",
  "partner",
  "outbound",
];

export function AnalyticsFilterBar() {
  const { filters, setFilters } = useAnalyticsFilters();
  const [draft, setDraft] = useState<AnalyticsFilters>(filters);

  useEffect(() => setDraft(filters), [filters]);

  const apply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft.date_from && draft.date_to && draft.date_from > draft.date_to) {
      return;
    }
    setFilters(draft);
  };

  const reset = () => {
    setDraft({});
    setFilters({});
  };

  return (
    <form className="analytics-filter-bar" onSubmit={apply}>
      <div className="analytics-filter-heading">
        <div>
          <SlidersHorizontal size={16} />
          <strong>Shared filters</strong>
          <span>Applied to analytics and lead explorer</span>
        </div>
        <button className="button button-text" type="button" onClick={reset}>
          <RotateCcw size={14} /> Reset
        </button>
      </div>
      <div className="analytics-filter-fields">
        <label className="field-label">
          Created from
          <input
            type="date"
            value={draft.date_from ?? ""}
            onChange={(event) =>
              setDraft({ ...draft, date_from: event.target.value || undefined })
            }
          />
        </label>
        <label className="field-label">
          Created through
          <input
            type="date"
            value={draft.date_to ?? ""}
            onChange={(event) =>
              setDraft({ ...draft, date_to: event.target.value || undefined })
            }
          />
        </label>
        <label className="field-label">
          Current stage
          <select
            value={draft.stage ?? ""}
            onChange={(event) =>
              setDraft({
                ...draft,
                stage: (event.target.value || undefined) as LeadStage | undefined,
              })
            }
          >
            <option value="">All stages</option>
            {stages.map((stage) => (
              <option key={stage} value={stage}>
                {formatStage(stage)}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Status
          <select
            value={draft.status ?? ""}
            onChange={(event) =>
              setDraft({
                ...draft,
                status: (event.target.value || undefined) as LeadStatus | undefined,
              })
            }
          >
            <option value="">All statuses</option>
            {statuses.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Acquisition source
          <select
            value={draft.source ?? ""}
            onChange={(event) =>
              setDraft({
                ...draft,
                source: (event.target.value || undefined) as
                  | AcquisitionSource
                  | undefined,
              })
            }
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {formatStage(source)}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Qualification
          <select
            value={
              draft.qualified === undefined ? "" : String(draft.qualified)
            }
            onChange={(event) =>
              setDraft({
                ...draft,
                qualified: event.target.value
                  ? event.target.value === "true"
                  : undefined,
              })
            }
          >
            <option value="">All leads</option>
            <option value="true">Qualified</option>
            <option value="false">Not qualified</option>
          </select>
        </label>
        <button className="button button-primary analytics-filter-submit" type="submit">
          Apply filters
        </button>
      </div>
      {draft.date_from && draft.date_to && draft.date_from > draft.date_to && (
        <p className="filter-validation-message" role="alert">
          The start date must be on or before the end date.
        </p>
      )}
    </form>
  );
}
