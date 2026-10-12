import { useCallback } from "react";
import { AlertTriangle, CircleX, Target } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { StatusPanel } from "../components/StatusPanel";
import { useApiResource } from "../hooks/useApiResource";
import { api } from "../lib/api";
import type { FunnelAnalytics } from "../types";
import { formatNumber, formatPercent, formatStage } from "../utils/format";

export function FunnelIntelligencePage({ datasetId }: { datasetId: string }) {
  const loader = useCallback(
    (signal: AbortSignal) => api.getFunnelAnalytics(datasetId, signal),
    [datasetId],
  );
  const resource = useApiResource(loader);
  const empty = resource.data?.total_leads === 0;

  return (
    <section className="page-content">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span /> FUNNEL INTELLIGENCE</div>
          <h1>See your pipeline<br className="mobile-break" /> as it is.</h1>
          <p className="page-intro">
            Understand where leads sit today, with no guesswork about yesterday.
          </p>
        </div>
        <div className="snapshot-pill"><Target size={15} /> Current-stage snapshot</div>
      </div>

      {resource.loading || resource.error || empty ? (
        <div className="content-card overview-status-card">
          <StatusPanel
            loading={resource.loading}
            error={resource.error}
            onRetry={resource.reload}
            empty={Boolean(empty && !resource.loading && !resource.error)}
            emptyTitle="No leads in this funnel"
            emptyMessage="Every stage will appear here once this dataset contains leads."
          />
        </div>
      ) : resource.data ? (
        <FunnelContent data={resource.data} />
      ) : null}
    </section>
  );
}

function FunnelContent({ data }: { data: FunnelAnalytics }) {
  return (
    <>
      <div className="metric-grid funnel-metrics">
        <MetricCard
          label="Leads in pipeline"
          value={formatNumber(data.total_leads)}
          supportingText="Current dataset snapshot"
          icon={Target}
          tone="lime"
        />
        <MetricCard
          label="Recorded as lost"
          value={formatNumber(data.loss_analysis.total_lost_leads)}
          supportingText="Based on current status"
          icon={CircleX}
          tone="orange"
        />
        <MetricCard
          label="Loss rate"
          value={formatPercent(data.loss_analysis.loss_rate)}
          supportingText="Lost leads ÷ all leads"
          icon={AlertTriangle}
          tone="dark"
        />
      </div>

      <section className="content-card funnel-card">
        <div className="card-heading funnel-card-heading">
          <div>
            <span className="card-kicker">CURRENT PIPELINE</span>
            <h2>Stage distribution</h2>
            <p>Bars show the share of this dataset currently recorded at each stage.</p>
          </div>
          <span className="snapshot-tag">Snapshot · {formatNumber(data.total_leads)} leads</span>
        </div>
        <div className="stage-list">
          {data.stage_distribution.map((stage, index) => (
            <div className="stage-row" key={stage.stage}>
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="stage-name">{formatStage(stage.stage)}</span>
              <div
                className="stage-track"
                role="meter"
                aria-label={`${formatStage(stage.stage)} share of dataset`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={stage.percentage_of_total}
              >
                <span
                  className={`stage-fill stage-fill-${index}`}
                  style={{ width: `${stage.percentage_of_total}%` }}
                />
              </div>
              <span className="stage-count">{formatNumber(stage.lead_count)}</span>
              <span className="stage-share">
                {formatPercent(stage.percentage_of_total)}
              </span>
            </div>
          ))}
        </div>
        <div className="funnel-note">
          <span className="note-icon"><AlertTriangle size={16} /></span>
          <div>
            <strong>This is a point-in-time view, not a drop-off report.</strong>
            <p>
              The API stores each lead’s current stage only. These counts cannot
              reconstruct historical transitions or exact stage-to-stage drop-offs.
            </p>
          </div>
        </div>
      </section>

      <section className="content-card loss-card">
        <div className="card-heading">
          <div>
            <span className="card-kicker">LOSS ANALYSIS</span>
            <h2>Lost leads by recorded stage</h2>
            <p>Grouped by the stage currently stored for leads marked lost.</p>
          </div>
          <span className="loss-total">{formatNumber(data.loss_analysis.total_lost_leads)} lost</span>
        </div>
        <div className="loss-stage-list">
          {data.loss_analysis.leads_by_stage.map((stage) => (
            <div className="loss-stage-row" key={stage.stage}>
              <span>{formatStage(stage.stage)}</span>
              <span className="loss-stage-count">{formatNumber(stage.lead_count)}</span>
              <span className="loss-stage-share">
                {formatPercent(stage.percentage_of_lost_leads)}
              </span>
            </div>
          ))}
        </div>
        <p className="loss-disclaimer">
          Loss reasons are not recorded in the source data and are not inferred here.
        </p>
      </section>
    </>
  );
}
