import { useI18n } from "../i18n";

interface Props {
  // friendly, translated headline (e.g. t("failed_load_groups"))
  title: string;
  // raw error text — shown demoted as muted detail so it's available for debugging but doesn't dominate
  detail?: string | null;
  // when provided, renders a primary Retry button (e.g. query.refetch)
  onRetry?: () => void;
  // optional secondary action, e.g. "← New session"
  action?: { label: string; onClick: () => void };
}

// Graceful failure UI for a failed query/mutation: a human headline up top, the raw error tucked
// underneath as muted small text, and explicit Retry / secondary actions — instead of dumping a raw
// Error.message at the user (issue #70).
export default function ErrorState({ title, detail, onRetry, action }: Props) {
  const { t } = useI18n();
  return (
    <div className="centered error-screen">
      <h2 className="error-title">{title}</h2>
      {detail && <p className="error-detail muted small">{detail}</p>}
      <div className="error-actions">
        {onRetry && (
          <button className="btn btn-accent" onClick={onRetry}>
            {t("retry")}
          </button>
        )}
        {action && (
          <button className="btn btn-ghost" onClick={action.onClick}>
            {action.label}
          </button>
        )}
      </div>
    </div>
  );
}
