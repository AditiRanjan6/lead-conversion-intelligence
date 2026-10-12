import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string;
  supportingText: string;
  icon: LucideIcon;
  tone?: "lime" | "dark" | "violet" | "orange";
}

export function MetricCard({
  label,
  value,
  supportingText,
  icon: Icon,
  tone = "lime",
}: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-card-top">
        <span className="metric-label">{label}</span>
        <span className={`metric-icon metric-icon-${tone}`}>
          <Icon size={18} strokeWidth={1.9} />
        </span>
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-support">{supportingText}</span>
    </article>
  );
}
