import { useCallback } from "react";
import {
  ArrowUpRight,
  BadgeCheck,
  CircleDollarSign,
  Download,
  UsersRound,
  Zap,
} from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { AnalyticsFilterBar } from "../components/AnalyticsFilterBar";
import { StageChart } from "../components/StageChart";
import { StatusPanel } from "../components/StatusPanel";
import { useApiResource } from "../hooks/useApiResource";
import { useAnalyticsFilters } from "../context/AnalyticsFilterContext";
import { api } from "../lib/api";
import { escapeCsvCell } from "../utils/csv";
import type { AnalyticsFilters, FunnelAnalytics, GrowthOverview } from "../types";
import {
  formatAmount,
  formatNumber,
  formatPercent,
  formatStage,
} from "../utils/format";

interface GrowthPageData {
  growth: GrowthOverview;
  funnel: FunnelAnalytics;
  previous?: GrowthOverview;
  previousRange?: { date_from: string; date_to: string };
}

function previousPeriod(
  filters: AnalyticsFilters,
): { date_from: string; date_to: string } | undefined {
  if (!filters.date_from || !filters.date_to) return undefined;
  const start = Date.parse(`${filters.date_from}T00:00:00Z`);
  const end = Date.parse(`${filters.date_to}T00:00:00Z`);
  const day = 24 * 60 * 60 * 1000;
  const length = Math.floor((end - start) / day) + 1;
  const previousEnd = start - day;
  return {
    date_from: new Date(previousEnd - (length - 1) * day).toISOString().slice(0, 10),
    date_to: new Date(previousEnd).toISOString().slice(0, 10),
  };
}

export function GrowthOverviewPage({ datasetId }: { datasetId: string }) {
  const { filters } = useAnalyticsFilters();
  const loader = useCallback(
    async (signal: AbortSignal): Promise<GrowthPageData> => {
      const previousRange = previousPeriod(filters);
      const [growth, funnel] = await Promise.all([
        api.getGrowthOverview(datasetId, filters, signal),
        api.getFunnelAnalytics(datasetId, filters, signal),
      ]);
      const previous = previousRange
        ? await api.getGrowthOverview(datasetId, { ...filters, ...previousRange }, signal)
        : undefined;
      return { growth, funnel, previous, previousRange };
    },
    [datasetId, filters],
  );
  const resource = useApiResource(loader);
  const isEmpty = resource.data?.growth.total_leads === 0;

  const downloadReport = () => {
    if (!resource.data) return;
    const { growth, funnel } = resource.data;
    const mostCommonStage = [...funnel.stage_distribution].sort(
      (left, right) => right.lead_count - left.lead_count,
    )[0];
    const rows: unknown[][] = [
      ["Lead Conversion Intelligence report"],
      ["Dataset ID", datasetId],
      ["Created at", new Date().toISOString()],
      ["Current-stage snapshot", "Historical stage transitions are not available."],
      ["Metric", "Value"],
      ["Total leads", growth.total_leads],
      ["Qualified leads", growth.qualified_leads],
      ["Qualification rate (%)", growth.qualification_rate],
      ["Converted leads", growth.converted_leads],
      ["Conversion rate (%)", growth.conversion_rate],
      ["Lost leads", growth.lost_leads],
      ["Converted deal value (currency unspecified)", growth.converted_deal_value],
      ["Most common current stage", mostCommonStage?.stage ?? ""],
      ["Most common current stage count", mostCommonStage?.lead_count ?? 0],
      ["Stage", "Current leads", "Share of filtered records (%)"],
      ...funnel.stage_distribution.map((stage) => [
        stage.stage,
        stage.lead_count,
        stage.percentage_of_total,
      ]),
      ["Data limitations", ...funnel.data_limitations],
    ];
    const contents = `\uFEFF${rows.map((row) => row.map(escapeCsvCell).join(",")).join("\r\n")}\r\n`;
    const url = URL.createObjectURL(
      new Blob([contents], { type: "text/csv;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `lead-conversion-report-${datasetId}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="page-content">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span /> GROWTH OVERVIEW</div>
          <h1>Know where growth<br className="mobile-break" /> is coming from.</h1>
          <p className="page-intro">
            A clear view of your pipeline health, qualification, and conversion.
          </p>
        </div>
        <div className="growth-actions">
          <button
            className="button button-secondary"
            onClick={downloadReport}
            disabled={!resource.data || resource.loading}
          >
            <Download size={15} /> Export report
          </button>
          <div className="live-pill"><span /> Live dataset metrics</div>
        </div>
      </div>

      <AnalyticsFilterBar />

      {resource.loading || resource.error || isEmpty ? (
        <div className="content-card overview-status-card">
          <StatusPanel
            loading={resource.loading}
            error={resource.error}
            onRetry={resource.reload}
            empty={Boolean(isEmpty && !resource.loading && !resource.error)}
            emptyTitle={filtersAreApplied(filters) ? "No leads match these filters" : "Your pipeline is clear"}
            emptyMessage={filtersAreApplied(filters) ? "Adjust the shared filters to see records." : "This dataset has no leads yet. Metrics will appear as data is added."}
          />
        </div>
      ) : resource.data ? (
        <>
          <div className="metric-grid">
            <MetricCard
              label="Total leads"
              value={formatNumber(resource.data.growth.total_leads)}
              supportingText="Matching filters"
              icon={UsersRound}
              tone="lime"
              definition="Count of leads in the selected dataset that match the shared filters."
              href="/leads"
            />
            <MetricCard
              label="Qualified"
              value={formatNumber(resource.data.growth.qualified_leads)}
              supportingText={`${formatPercent(resource.data.growth.qualification_rate)} of matching leads`}
              icon={BadgeCheck}
              tone="violet"
              definition="Qualified leads divided by all leads matching the shared filters."
              href="/leads?qualified=true"
            />
            <MetricCard
              label="Converted"
              value={formatNumber(resource.data.growth.converted_leads)}
              supportingText={`${formatPercent(resource.data.growth.conversion_rate)} of matching leads`}
              icon={Zap}
              tone="dark"
              definition="Converted leads divided by all leads matching the shared filters."
              href="/leads?status=converted"
            />
            <MetricCard
              label="Converted deal value"
              value={formatAmount(resource.data.growth.converted_deal_value)}
              supportingText="Currency not specified by the API"
              icon={CircleDollarSign}
              tone="orange"
              definition="Sum of converted-lead deal values matching the shared filters. The API does not specify a currency."
              href="/leads?status=converted"
            />
          </div>

          <section className="content-card executive-summary">
            <span className="card-kicker">EXECUTIVE SUMMARY</span>
            <h2>At a glance</h2>
            <p>
              Dataset <strong>{datasetId}</strong> contains{" "}
              <strong>{formatNumber(resource.data.growth.total_leads)}</strong>{" "}
              matching leads, including{" "}
              <strong>{formatNumber(resource.data.growth.qualified_leads)}</strong>{" "}
              qualified and{" "}
              <strong>{formatNumber(resource.data.growth.converted_leads)}</strong>{" "}
              converted records. The most common current stage is{" "}
              <strong>
                {formatStage(
                  [...resource.data.funnel.stage_distribution].sort(
                    (left, right) => right.lead_count - left.lead_count,
                  )[0]?.stage ?? "new",
                )}
              </strong>
              . This is a current-state summary; stage-transition history is not
              available.
            </p>
          </section>

          {resource.data.previous && resource.data.previousRange && (
            <section className="content-card comparison-card">
              <div className="card-heading">
                <div>
                  <span className="card-kicker">PERIOD COMPARISON</span>
                  <h2>Compared with the preceding period</h2>
                  <p>
                    {resource.data.previousRange.date_from} to{" "}
                    {resource.data.previousRange.date_to}; same duration and
                    non-date filters.
                  </p>
                </div>
              </div>
              <div className="comparison-grid">
                <ComparisonItem
                  label="Leads"
                  current={resource.data.growth.total_leads}
                  previous={resource.data.previous.total_leads}
                />
                <ComparisonItem
                  label="Qualified"
                  current={resource.data.growth.qualified_leads}
                  previous={resource.data.previous.qualified_leads}
                />
                <ComparisonItem
                  label="Conversion rate"
                  current={resource.data.growth.conversion_rate}
                  previous={resource.data.previous.conversion_rate}
                  percentage
                />
                <ComparisonItem
                  label="Converted deal value"
                  current={resource.data.growth.converted_deal_value}
                  previous={resource.data.previous.converted_deal_value}
                />
              </div>
            </section>
          )}

          <div className="content-grid">
            <section className="content-card chart-card">
              <div className="card-heading">
                <div>
                  <span className="card-kicker">PIPELINE SNAPSHOT</span>
                  <h2>Leads by current stage</h2>
                  <p>Current filtered distribution, not historical stage movement.</p>
                </div>
                <div className="chart-legend">
                  <span><i className="legend-bar" /> Leads</span>
                  <span><i className="legend-line" /> Share</span>
                </div>
              </div>
              <StageChart data={resource.data.funnel.stage_distribution} />
              <div className="chart-caption">
                <span>Stage</span>
                <span>
                  <ArrowUpRight size={14} />
                  Share of matching leads
                </span>
              </div>
            </section>

            <section className="content-card conversion-card">
              <div className="card-heading">
                <div>
                  <span className="card-kicker">CONVERSION HEALTH</span>
                  <h2>Quality at a glance</h2>
                  <p>Rates are calculated from all leads matching the shared filters.</p>
                </div>
              </div>
              <div className="health-stat">
                <div className="health-stat-icon health-stat-icon-lime">
                  <BadgeCheck size={18} />
                </div>
                <div className="health-stat-copy">
                  <span>Qualification rate</span>
                  <strong>{formatPercent(resource.data.growth.qualification_rate)}</strong>
                </div>
              </div>
              <div className="health-divider" />
              <div className="health-stat">
                <div className="health-stat-icon health-stat-icon-dark">
                  <Zap size={18} />
                </div>
                <div className="health-stat-copy">
                  <span>Conversion rate</span>
                  <strong>{formatPercent(resource.data.growth.conversion_rate)}</strong>
                </div>
              </div>
              <div className="conversion-footnote">
                <span className="footnote-dot" />
                <span>
                  {formatNumber(resource.data.growth.lost_leads)} leads currently
                  recorded as lost.
                </span>
              </div>
            </section>
          </div>
        </>
      ) : null}
    </section>
  );
}

function filtersAreApplied(filters: AnalyticsFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined && value !== "");
}

function ComparisonItem({
  label,
  current,
  previous,
  percentage = false,
}: {
  label: string;
  current: number;
  previous: number;
  percentage?: boolean;
}) {
  const difference = current - previous;
  const value = percentage
    ? `${difference > 0 ? "+" : ""}${difference.toFixed(2)} pp`
    : `${difference > 0 ? "+" : ""}${formatNumber(difference)}`;
  return (
    <div className="comparison-item">
      <span>{label}</span>
      <strong className={difference > 0 ? "comparison-positive" : difference < 0 ? "comparison-negative" : ""}>
        {value}
      </strong>
      <small>
        Current {percentage ? formatPercent(current) : formatNumber(current)} ·
        prior {percentage ? formatPercent(previous) : formatNumber(previous)}
      </small>
    </div>
  );
}
