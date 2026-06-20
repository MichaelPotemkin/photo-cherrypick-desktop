import { useState } from "react";
import type { DecisionAction, Group, ViewMode } from "../api";
import { useI18n } from "../i18n";
import { AxisGrid } from "./AxisBars";

interface Props {
  group: Group;
  mode: ViewMode; // for the localized group label (burst vs scene)
  index: number; // index within group.photos
  groupNumber: number; // 1-based position of this group in the session
  groupCount: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onPrevGroup: () => void;
  onNextGroup: () => void;
  onJump: (index: number) => void;
  onDecide: (action: DecisionAction) => void;
}

const ZOOM = 2.6; // magnification on hover — moderate, so it's easy to read detail

export default function Lightbox({
  group,
  mode,
  index,
  groupNumber,
  groupCount,
  onClose,
  onPrev,
  onNext,
  onPrevGroup,
  onNextGroup,
  onJump,
  onDecide,
}: Props) {
  const { t } = useI18n();
  // Hover magnifier: zoom in where the cursor is and pan as it moves.
  const [hover, setHover] = useState(false);
  const [origin, setOrigin] = useState("50% 50%");

  const photo = group.photos[index];
  if (!photo) return null;

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 100;
    const y = ((e.clientY - r.top) / r.height) * 100;
    setOrigin(`${x}% ${y}%`);
  }

  const n = group.photos.length;
  const groupLabel =
    mode === "scene"
      ? n > 1
        ? t("label_scene", { n })
        : t("label_unique")
      : n > 1
        ? t("label_burst_pick", { n })
        : t("label_single");

  const caption =
    `${index + 1}/${n} · ${photo.filename} · ${photo.when} · ` +
    t("score", { n: Math.round(photo.overall * 100) }) +
    (photo.reasons.length ? ` · ${photo.reasons.map((r) => t(`reason:${r}`)).join(" · ")}` : "") +
    (photo.suggested ? ` ${t("suggested_caption")}` : "");

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <div className="lightbox" onClick={(e) => e.stopPropagation()}>
        <button className="lightbox-close" onClick={onClose} title={t("close_esc")}>
          ✕
        </button>

        {/* Group navigation bar */}
        <div className="lightbox-groupnav">
          <button className="btn btn-ghost groupnav-btn" onClick={onPrevGroup} title={t("prev_group_title")}>
            {t("prev_group")}
          </button>
          <span className="groupnav-label">
            {t("group")} {groupNumber}/{groupCount} — {groupLabel}
            {group.close_call && <span className="close-call-badge">{t("close_call")}</span>}
          </span>
          <button className="btn btn-ghost groupnav-btn" onClick={onNextGroup} title={t("next_group_title")}>
            {t("next_group")}
          </button>
        </div>

        <div className="lightbox-main">
          <button className="nav-arrow nav-prev" onClick={onPrev} title={t("prev_photo_title")}>
            ‹
          </button>

          <div
            className={`lightbox-stage${hover ? " zooming" : ""}`}
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}
            onMouseMove={onMove}
            title={t("hover_zoom")}
          >
            <img
              className="lightbox-img"
              src={photo.preview_url}
              alt={photo.filename}
              draggable={false}
              style={hover ? { transform: `scale(${ZOOM})`, transformOrigin: origin } : undefined}
            />
          </div>

          <button className="nav-arrow nav-next" onClick={onNext} title={t("next_photo_title")}>
            ›
          </button>
        </div>

        <div className="lightbox-caption">{caption}</div>

        <div className="lightbox-actions">
          <button
            className={`btn btn-fav${photo.state === "favorite" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "favorite" ? "undo" : "favorite")}
            aria-pressed={photo.state === "favorite"}
            title={`${photo.state === "favorite" ? t("remove_favorite") : t("mark_favorite")} (F)`}
          >
            {t("btn_fav")}
            <kbd className="btn-kbd">f</kbd>
          </button>
          <button
            className={`btn btn-maybe${photo.state === "maybe" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "maybe" ? "undo" : "maybe")}
            aria-pressed={photo.state === "maybe"}
            title={`${photo.state === "maybe" ? t("remove_maybe") : t("mark_maybe")} (M)`}
          >
            {t("btn_maybe")}
            <kbd className="btn-kbd">m</kbd>
          </button>
          <button
            className={`btn btn-del${photo.state === "delete" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "delete" ? "undo" : "delete")}
            aria-pressed={photo.state === "delete"}
            title={`${photo.state === "delete" ? t("remove_trash") : t("mark_trash")} (X)`}
          >
            {t("btn_trash")}
            <kbd className="btn-kbd">x</kbd>
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => onDecide("undo")}
            disabled={photo.state === "none"}
            title={`${t("clear_label")} (U)`}
          >
            {t("btn_undo")}
            <kbd className="btn-kbd">u</kbd>
          </button>
        </div>

        <div className="lightbox-panel">
          <h4 className="panel-title">{t("axes_title")}</h4>
          <AxisGrid axes={photo.axes} />
        </div>

        <div className="filmstrip">
          {group.photos.map((p, i) => (
            <button
              key={p.id}
              className={`filmstrip-thumb${i === index ? " active" : ""}${
                p.suggested ? " suggested" : ""
              } film-${p.state}`}
              onClick={() => onJump(i)}
              title={p.filename}
            >
              <img src={p.preview_url} alt={p.filename} loading="lazy" />
              {p.suggested && <span className="film-badge">★</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
