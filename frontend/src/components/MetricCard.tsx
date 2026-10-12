import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

interface MetricCardProps {
  label: string;
  value: string;
  supportingText: string;
  icon: LucideIcon;
  tone?: "lime" | "dark" | "violet" | "orange";
  definition: string;
  href?: string;
}

export function MetricCard({
  label,
  value,
  supportingText,
  icon: Icon,
  tone = "lime",
  definition,
  href,
}: MetricCardProps) {
  const card = (
    <article className="metric-card">
      <div className="metric-card-top">
        <span className="metric-label">{label}</span>
        <span
          className="metric-definition"
          tabIndex={0}
          aria-label={`${label} definition: ${definition}`}
          title={definition}
        >
          i
        </span>
        <span className={`metric-icon metric-icon-${tone}`}>
          <Icon size={18} strokeWidth={1.9} />
        </span>
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-support">{supportingText}</span>
    </article>
  );

  return href ? (
    <Link className="metric-card-link" to={href} aria-label={`View leads: ${label}`}>
      {card}
    </Link>
  ) : (
    card
  );
}
