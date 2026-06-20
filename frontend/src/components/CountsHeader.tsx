import { useEffect, useState } from "react";
import type { Counts, ViewMode } from "../api";
import { useI18n } from "../i18n";
import LangToggle from "./LangToggle";

interface Props {
  title: string;
  nTotal: number;
  nGroups: number;
  counts: Counts;
  mode: ViewMode;
  onSetMode: (mode: ViewMode) => void;
  hideSorted: boolean;
  onToggleHide: () => void;
  onExportZip: () => void;
  nSuggestions: number;
  onAcceptSuggestions: () => void;
  onRename: (title: string) => void;
  onHome: () => void;
}

export default function CountsHeader({
  title,
  nTotal,
  nGroups,
  counts,
  mode,
  onSetMode,
  hideSorted,
  onToggleHide,
  onExportZip,
  nSuggestions,
  onAcceptSuggestions,
  onRename,
  onHome,
}: Props) {
  const { t } = useI18n();
  const nPicks = counts.favorite + counts.maybe;

  // Inline rename of the session title.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [confirmAccept, setConfirmAccept] = useState(false);
  useEffect(() => {
    if (!editing) setDraft(title); // keep in sync when the title changes elsewhere
  }, [title, editing]);

  function commit() {
    setEditing(false);
    const next = draft.trim();
    if (next && next !== title) onRename(next);
    else setDraft(title);
  }

  const subtitle =
    mode === "feed"
      ? t("sub_feed", { n: counts.favorite })
      : mode === "scene"
        ? t("sub_scenes", { n: nGroups })
        : t("sub_bursts", { n: nGroups });

  return (
    <header className="counts-header">
      <div className="counts-header-row">
        <div className="counts-title">
          <button className="btn btn-ghost home-btn" onClick={onHome} title={t("new_session")}>
            ←
          </button>
          <div>
            {editing ? (
              <input
                className="title-edit"
                value={draft}
                autoFocus
                maxLength={200}
                aria-label={t("session_name")}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  else if (e.key === "Escape") {
                    setEditing(false);
                    setDraft(title);
                  }
                }}
              />
            ) : (
              <div className="title-line">
                {title}
                <button
                  className="btn btn-ghost rename-btn"
                  onClick={() => setEditing(true)}
                  title={t("rename_session")}
                  aria-label={t("rename_session")}
                >
                  ✎
                </button>
              </div>
            )}
            <div className="muted small">
              {t("n_photos", { n: nTotal })} · {subtitle}
            </div>
          </div>
        </div>

        <div className="pills">
          <span className="pill">{t("undecided", { n: counts.none })}</span>
          <span className="pill pill-fav">{t("kept", { n: counts.favorite })}</span>
          <span className="pill pill-maybe">{t("maybe_pill", { n: counts.maybe })}</span>
          <span className="pill pill-del">{t("trash_pill", { n: counts.delete })}</span>
        </div>

        <div className="header-actions">
          <LangToggle />
          <div className="mode-toggle" role="group" aria-label={t("aria_grouping_mode")}>
            <button
              type="button"
              className={`mode-btn${mode === "burst" ? " active" : ""}`}
              aria-pressed={mode === "burst"}
              onClick={() => onSetMode("burst")}
              title={t("mode_burst_title")}
            >
              {t("mode_burst")}
            </button>
            <button
              type="button"
              className={`mode-btn${mode === "scene" ? " active" : ""}`}
              aria-pressed={mode === "scene"}
              onClick={() => onSetMode("scene")}
              title={t("mode_scene_title")}
            >
              {t("mode_scene")}
            </button>
            <button
              type="button"
              className={`mode-btn${mode === "feed" ? " active" : ""}`}
              aria-pressed={mode === "feed"}
              onClick={() => onSetMode("feed")}
              title={t("mode_feed_title")}
            >
              {t("mode_feed")}
            </button>
          </div>

          {confirmAccept ? (
            <div className="accept-confirm">
              <span className="muted small">{t("accept_confirm", { n: nSuggestions })}</span>
              <button
                className="btn btn-sm btn-accent"
                onClick={() => {
                  onAcceptSuggestions();
                  setConfirmAccept(false);
                }}
              >
                {t("confirm")}
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => setConfirmAccept(false)}>
                {t("cancel")}
              </button>
            </div>
          ) : (
            <button
              className="btn btn-ghost"
              disabled={nSuggestions === 0}
              onClick={() => setConfirmAccept(true)}
              title={nSuggestions === 0 ? t("accept_none_title") : t("accept_title")}
            >
              {t("accept_picks")}
              {nSuggestions ? ` (${nSuggestions})` : ""}
            </button>
          )}

          <button
            className={`btn ${hideSorted ? "btn-accent" : "btn-ghost"}`}
            onClick={onToggleHide}
          >
            {hideSorted ? t("show_all") : t("hide_sorted")}
          </button>
          <button
            className="btn btn-accent"
            onClick={onExportZip}
            disabled={nPicks === 0}
            title={nPicks === 0 ? t("download_disabled_title") : t("download_title")}
          >
            {t("download_picks")}
            {nPicks ? ` (${nPicks})` : ""}
          </button>
        </div>
      </div>
    </header>
  );
}
