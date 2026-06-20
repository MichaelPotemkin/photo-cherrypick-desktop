import type { SessionDetail, SessionStatus } from "../api";
import { useI18n } from "../i18n";

interface Props {
  session: SessionDetail;
}

const STATUS_KEY: Record<SessionStatus, string> = {
  pending: "st_pending",
  processing: "st_processing",
  ready: "st_ready",
  error: "st_err",
};

export default function Progress({ session }: Props) {
  const { t } = useI18n();
  const { status, n_done, n_total } = session;
  const pct = n_total > 0 ? Math.round((n_done / n_total) * 100) : 0;

  return (
    <div className="progress-screen">
      <div className="progress-card">
        <h2>{session.title || t("analyzing")}</h2>
        <p className="muted status-line">
          {t("status_label")}: <strong>{t(STATUS_KEY[status])}</strong>
        </p>
        <div className="progressbar-track">
          <div className="progressbar-fill" style={{ width: `${pct}%` }} />
        </div>
        <p className="muted">{t("photos_pct", { done: n_done, total: n_total, pct })}</p>
      </div>
    </div>
  );
}
