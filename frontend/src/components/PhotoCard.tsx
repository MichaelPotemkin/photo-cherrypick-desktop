import { memo } from "react";
import type { DecisionAction, Photo } from "../api";
import { useI18n } from "../i18n";
import { MiniBar } from "./AxisBars";

interface Props {
  photo: Photo;
  selected: boolean;
  onOpen: () => void;
  onDecide: (action: DecisionAction) => void;
  cardRef?: (el: HTMLDivElement | null) => void;
}

// The 5 category mini-bars shown on each card (label is a translation key suffix).
const CAT_BARS: { label: string; key: keyof Photo["cats"] }[] = [
  { label: "Focus", key: "focus" },
  { label: "Subject", key: "subject" },
  { label: "Compos", key: "composition" },
  { label: "Expo", key: "exposure" },
  { label: "Aesth", key: "aesthetic" },
];

function PhotoCardImpl({ photo, selected, onOpen, onDecide, cardRef }: Props) {
  const { t } = useI18n();
  const badge =
    photo.state === "favorite"
      ? t("badge_kept")
      : photo.state === "delete"
        ? t("badge_trash")
        : photo.state === "maybe"
          ? t("badge_maybe")
          : "";

  // tooltip / aria text for each action, toggling between mark and un-mark
  const favTip = t(photo.state === "favorite" ? "remove_favorite" : "mark_favorite");
  const maybeTip = t(photo.state === "maybe" ? "remove_maybe" : "mark_maybe");
  const trashTip = t(photo.state === "delete" ? "remove_trash" : "mark_trash");

  return (
    <div
      ref={cardRef}
      className={`card card-${photo.state}${selected ? " card-selected" : ""}`}
    >
      <div className="card-thumb" onClick={onOpen}>
        <img src={photo.preview_url} alt={photo.filename} loading="lazy" />
        {photo.suggested && <span className="badge badge-suggested">{t("badge_suggested")}</span>}
        {badge && (
          <span className={`badge badge-state badge-${photo.state}`}>{badge}</span>
        )}
      </div>

      <div className="card-body">
        <div className="card-meta">
          <span className="card-score">{t("score", { n: Math.round(photo.overall * 100) })}</span>
          {photo.is_bw && <span className="tag-bw">{t("bw")}</span>}
        </div>
        {photo.reasons.length > 0 && (
          <div className="card-reasons">
            {photo.reasons.map((r) => t(`reason:${r}`)).join(" · ")}
          </div>
        )}

        <div className="card-bars">
          {CAT_BARS.map((c) => (
            <MiniBar key={c.key} label={t(`cat:${c.label}`)} value={photo.cats[c.key]} />
          ))}
        </div>

        <div className="card-actions">
          {/* Icon-only on the dense card grid: equal width, never wraps, identical in every
              language. The full label lives in the hover tooltip (data-tip) and aria-label. */}
          <button
            className={`btn btn-sm btn-fav${photo.state === "favorite" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "favorite" ? "undo" : "favorite")}
            aria-pressed={photo.state === "favorite"}
            aria-label={favTip}
            data-tip={`${favTip} (F)`}
          >
            {t("btn_fav_short")}
            <kbd className="btn-kbd">f</kbd>
          </button>
          <button
            className={`btn btn-sm btn-maybe${photo.state === "maybe" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "maybe" ? "undo" : "maybe")}
            aria-pressed={photo.state === "maybe"}
            aria-label={maybeTip}
            data-tip={`${maybeTip} (M)`}
          >
            {t("btn_maybe_short")}
            <kbd className="btn-kbd">m</kbd>
          </button>
          <button
            className={`btn btn-sm btn-del${photo.state === "delete" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "delete" ? "undo" : "delete")}
            aria-pressed={photo.state === "delete"}
            aria-label={trashTip}
            data-tip={`${trashTip} (X)`}
          >
            {t("btn_trash_short")}
            <kbd className="btn-kbd">x</kbd>
          </button>
          <button
            className="btn btn-sm btn-ghost"
            onClick={() => onDecide("undo")}
            disabled={photo.state === "none"}
            aria-label={t("clear_label")}
            data-tip={`${t("clear_label")} (U)`}
          >
            {t("btn_undo_short")}
            <kbd className="btn-kbd">u</kbd>
          </button>
        </div>
      </div>
    </div>
  );
}

export default memo(PhotoCardImpl);
