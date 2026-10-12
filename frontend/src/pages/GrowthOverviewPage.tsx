import { useCallback } from "react";
import {
  ArrowUpRight,
  BadgeCheck,
  CircleDollarSign,
  UsersRound,
  Zap,
} from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { StageChart } from "../components/StageChart";
import { StatusPanel } from "../components/StatusPanel";
import { useApiResource } from "../hooks/useApiResource";
import { api } from "../lib/api";
import type { FunnelAnalytics, GrowthOverview } from "../types";
import { formatAmount, formatNumber, formatPercent } from "../utils/format";

interface GrowthPageData {
  growth: GrowthOverview;
  funnel: FunnelAnalytics;
}

export function GrowthOverviewPage({ datasetId }: { datasetId: string }) {
  const loader = useCallback(
    async (signal: AbortSignal): Promise<GrowthPageData> => {
      const [growth, funnel] = await Promise.all([
        api.getGrowthOverview(datasetId, signal),
        api.getFunnelAnalytics(datasetId, signal),
      ]);
      return { growth, funnel };
    },
    [datasetId],
  );
  const resource = useApiResource(loader);
  const isEmpty = resource.data?.growth.total_leads === 0;

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
        <div className="live-pill"><span /> Live dataset metrics</div>
      </div>

      {resource.loading || resource.error || isEmpty ? (
        <div className="content-card overview-status-card">
          <StatusPanel
            loading={resource.loading}
            error={resource.error}
            onRetry={resource.reload}
            empty={Boolean(isEmpty && !resource.loading && !resource.error)}
            emptyTitle="Your pipeline is clear"
            emptyMessage="This dataset has no leads yet. Metrics will appear as data is added."
          />
        </div>
      ) : resource.data ? (
        <>
          <div className="metric-grid">
            <MetricCard
              label="Total leads"
              value={formatNumber(resource.data.growth.total_leads)}
              supportingText="In this dataset"
              icon={UsersRound}
              tone="lime"
            />
            <MetricCard
              label="Qualified"
              value={formatNumber(resource.data.growth.qualified_leads)}
              supportingText={`${formatPercent(resource.data.growth.qualification_rate)} of all leads`}
              icon={BadgeCheck}
              tone="violet"
            />
            <MetricCard
              label="Converted"
              value={formatNumber(resource.data.growth.converted_leads)}
              supportingText={`${formatPercent(resource.data.growth.conversion_rate)} conversion rate`}
              icon={Zap}
              tone="dark"
            />
            <MetricCard
              label="Converted deal value"
              value={formatAmount(resource.data.growth.converted_deal_value)}
              supportingText="Currency not specified by the API"
              icon={CircleDollarSign}
              tone="orange"
            />
          </div>

          <div className="content-grid">
            <section className="content-card chart-card">
              <div className="card-heading">
                <div>
                  <span className="card-kicker">PIPELINE SNAPSHOT</span>
                  <h2>Leads by current stage</h2>
                  <p>Current dataset distribution, not historical stage movement.</p>
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
                  Share of dataset
                </span>
              </div>
            </section>

            <section className="content-card conversion-card">
              <div className="card-heading">
                <div>
                  <span className="card-kicker">CONVERSION HEALTH</span>
                  <h2>Quality at a glance</h2>
                  <p>Rates are calculated from all leads in this dataset.</p>
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
