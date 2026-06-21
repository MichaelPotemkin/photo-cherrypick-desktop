import { useEffect, useState } from "react";
import type { Counts, ViewMode } from "../api";
import { useI18n, tVariants } from "../i18n";
import HelpButton from "./HelpGuide";
import LangToggle from "./LangToggle";
import StableLabel from "./StableLabel";
import ConfirmModal from "./ConfirmModal";

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
  // Count suffix shown inside the Accept/Download buttons (omitted at zero). Kept identical on the live
  // label and its reserved variants so the button stays the same width across languages — see StableLabel.
  const acceptSuffix = nSuggestions ? ` (${nSuggestions})` : "";
  const downloadSuffix = nPicks ? ` (${nPicks})` : "";

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
          <button
            className="btn btn-ghost home-btn tip-start"
            onClick={onHome}
            aria-label={t("new_session")}
            data-tip={t("new_session")}
          >
            ←
          </button>
          <div className="title-block">
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
                <span className="title-text" title={title}>
                  {title}
                </span>
                <button
                  className="btn btn-ghost rename-btn"
                  onClick={() => setEditing(true)}
                  data-tip={t("rename_session")}
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
          <HelpButton />
          <LangToggle />
          <div className="mode-toggle" role="group" aria-label={t("aria_grouping_mode")}>
            <button
              type="button"
              className={`mode-btn${mode === "burst" ? " active" : ""}`}
              aria-pressed={mode === "burst"}
              onClick={() => onSetMode("burst")}
              data-tip={t("mode_burst_title")}
            >
              {t("mode_burst")}
            </button>
            <button
              type="button"
              className={`mode-btn${mode === "scene" ? " active" : ""}`}
              aria-pressed={mode === "scene"}
              onClick={() => onSetMode("scene")}
              data-tip={t("mode_scene_title")}
            >
              {t("mode_scene")}
            </button>
            <button
              type="button"
              className={`mode-btn${mode === "feed" ? " active" : ""}`}
              aria-pressed={mode === "feed"}
              onClick={() => onSetMode("feed")}
              data-tip={t("mode_feed_title")}
            >
              {t("mode_feed")}
            </button>
          </div>

          <button
            className="btn btn-ghost"
            disabled={nSuggestions === 0}
            onClick={() => setConfirmAccept(true)}
            data-tip={nSuggestions === 0 ? t("accept_none_title") : t("accept_title")}
          >
            <StableLabel
              text={`${t("accept_picks")}${acceptSuffix}`}
              reserve={tVariants("accept_picks").map((v) => `${v}${acceptSuffix}`)}
            />
          </button>

          <button
            className={`btn ${hideSorted ? "btn-accent" : "btn-ghost"}`}
            onClick={onToggleHide}
            data-tip={hideSorted ? t("show_all_title") : t("hide_sorted_title")}
          >
            <StableLabel
              text={hideSorted ? t("show_all") : t("hide_sorted")}
              reserve={[...tVariants("hide_sorted"), ...tVariants("show_all")]}
            />
          </button>
          <button
            className="btn btn-accent"
            onClick={onExportZip}
            disabled={nPicks === 0}
            data-tip={nPicks === 0 ? t("download_disabled_title") : t("download_title")}
          >
            <StableLabel
              text={`${t("download_picks")}${downloadSuffix}`}
              reserve={tVariants("download_picks").map((v) => `${v}${downloadSuffix}`)}
            />
          </button>
        </div>
      </div>

      {confirmAccept && (
        <ConfirmModal
          message={t("accept_confirm", { n: nSuggestions })}
          confirmLabel={t("confirm")}
          cancelLabel={t("cancel")}
          onConfirm={() => {
            onAcceptSuggestions();
            setConfirmAccept(false);
          }}
          onCancel={() => setConfirmAccept(false)}
        />
      )}
    </header>
  );
}
