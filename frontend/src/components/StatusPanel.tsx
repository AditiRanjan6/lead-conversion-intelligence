import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";

interface StatusPanelProps {
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
}

export function StatusPanel({
  loading = false,
  error = null,
  onRetry,
  empty = false,
  emptyTitle = "No data to show",
  emptyMessage = "This registered dataset has no leads yet.",
}: StatusPanelProps) {
  if (loading) {
    return (
      <div className="status-panel" role="status">
        <LoaderCircle className="status-icon status-icon-spin" size={22} />
        <strong>Loading live analytics</strong>
        <span>Fetching the selected dataset from the API.</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="status-panel status-panel-error" role="alert">
        <AlertCircle className="status-icon" size={22} />
        <strong>We couldn’t load this data</strong>
        <span>{error}</span>
        {onRetry && (
          <button className="button button-secondary status-retry" onClick={onRetry}>
            <RefreshCw size={15} />
            Try again
          </button>
        )}
      </div>
    );
  }

  if (empty) {
    return (
      <div className="status-panel">
        <div className="empty-mark">0</div>
        <strong>{emptyTitle}</strong>
        <span>{emptyMessage}</span>
      </div>
    );
  }

  return null;
}
