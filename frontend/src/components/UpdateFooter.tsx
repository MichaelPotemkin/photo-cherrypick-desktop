import { useI18n } from "../i18n";
import { useUpdater } from "../useUpdater";

// Fixed strip at the bottom of the screen that morphs with update state:
//   idle        → small "version x.y.z"
//   downloading → progress bar
//   ready        → "Update ready" button (the in-app replacement for the old native OS dialog)
// Renders nothing outside the packaged app (no version, nothing downloading).
export default function UpdateFooter() {
  const { version, stage, percent, newVersion, relaunch } = useUpdater();
  const { t } = useI18n();

  if (stage === "ready") {
    return (
      <div className="update-footer">
        <button
          className="btn btn-sm btn-accent update-ready-btn tip-up"
          onClick={relaunch}
          data-tip={t("update_relaunch_tip")}
        >
          ⬆ {t("update_ready")}
          {newVersion ? ` (${newVersion})` : ""}
        </button>
      </div>
    );
  }

  if (stage === "downloading") {
    return (
      <div className="update-footer">
        <div className="update-progress" role="status" aria-live="polite">
          <span className="muted small">
            {t("update_downloading")}
            {percent != null ? ` ${percent}%` : "…"}
          </span>
          <div className="update-bar-track">
            <div
              className={`update-bar-fill${percent == null ? " indeterminate" : ""}`}
              style={percent != null ? { width: `${percent}%` } : undefined}
            />
          </div>
        </div>
      </div>
    );
  }

  if (stage === "error") {
    // A background update check failed (offline, unreachable, bad signature). Surface a small,
    // non-disruptive note instead of silently swallowing it (#47) — the app keeps working.
    return (
      <div className="update-footer">
        <span className="muted small">⚠ {t("update_error")}</span>
      </div>
    );
  }

  if (!version) return null; // idle outside Tauri / version unknown → nothing to show

  return (
    <div className="update-footer">
      <span className="muted small version-label">{t("version_label", { v: version })}</span>
    </div>
  );
}
