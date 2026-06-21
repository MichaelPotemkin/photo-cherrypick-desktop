import { useEffect, useRef, useState } from "react";
import type { DecisionAction, Group, ViewMode } from "../api";
import { useI18n } from "../i18n";
import { buildGroupLabel } from "../lib/groupLabel";
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

  // Focus management: move focus into the dialog on open, trap Tab inside it, and restore focus to
  // the trigger on close. Only Tab is intercepted — Esc / arrows / f-m-x-u stay with the session's
  // global keyboard handler (useKeyboard), which owns them while the lightbox is open. Runs once for
  // the lightbox's lifetime (it stays mounted across photo navigation), so focus isn't re-grabbed on
  // every frame change.
  const lightboxRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    lightboxRef.current?.focus();

    const focusables = (): HTMLElement[] =>
      Array.from(
        lightboxRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return; // let the global handler own everything else
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const act = document.activeElement;
      if (e.shiftKey && (act === first || act === lightboxRef.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && act === last) {
        e.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prevFocus?.focus?.();
    };
  }, []);

  const photo = group.photos[index];
  if (!photo) return null;

  // tooltip / aria text for each action, toggling between mark and un-mark
  const favTip = t(photo.state === "favorite" ? "remove_favorite" : "mark_favorite");
  const maybeTip = t(photo.state === "maybe" ? "remove_maybe" : "mark_maybe");
  const trashTip = t(photo.state === "delete" ? "remove_trash" : "mark_trash");

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 100;
    const y = ((e.clientY - r.top) / r.height) * 100;
    setOrigin(`${x}% ${y}%`);
  }

  const n = group.photos.length;
  const groupLabel = buildGroupLabel(t, mode, n);

  const caption =
    `${index + 1}/${n} · ${photo.filename} · ${photo.when} · ` +
    t("score", { n: Math.round(photo.overall * 100) }) +
    (photo.reasons.length ? ` · ${photo.reasons.map((r) => t(`reason:${r}`)).join(" · ")}` : "") +
    (photo.suggested ? ` ${t("suggested_caption")}` : "");

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <div
        className="lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={groupLabel}
        tabIndex={-1}
        ref={lightboxRef}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="lightbox-close"
          onClick={onClose}
          aria-label={t("close_esc")}
          data-tip={t("close_esc")}
        >
          ✕
        </button>

        {/* Group navigation bar */}
        <div className="lightbox-groupnav">
          <button className="btn btn-ghost groupnav-btn" onClick={onPrevGroup} data-tip={t("prev_group_title")}>
            {t("prev_group")}
          </button>
          <span className="groupnav-label">
            {t("group")} {groupNumber}/{groupCount} — {groupLabel}
            {group.close_call && (
              <span className="close-call-badge" data-tip={t("close_call_title")}>
                {t("close_call")}
              </span>
            )}
          </span>
          <button className="btn btn-ghost groupnav-btn" onClick={onNextGroup} data-tip={t("next_group_title")}>
            {t("next_group")}
          </button>
        </div>

        <div className="lightbox-main">
          <button
            className="nav-arrow nav-prev"
            onClick={onPrev}
            aria-label={t("prev_photo_title")}
            data-tip={t("prev_photo_title")}
          >
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

          <button
            className="nav-arrow nav-next"
            onClick={onNext}
            aria-label={t("next_photo_title")}
            data-tip={t("next_photo_title")}
          >
            ›
          </button>
        </div>

        <div className="lightbox-caption">{caption}</div>

        <div className="lightbox-actions">
          <button
            className={`btn btn-fav${photo.state === "favorite" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "favorite" ? "undo" : "favorite")}
            aria-pressed={photo.state === "favorite"}
            aria-label={favTip}
            data-tip={`${favTip} (F)`}
          >
            {t("btn_fav")}
            <kbd className="btn-kbd">f</kbd>
          </button>
          <button
            className={`btn btn-maybe${photo.state === "maybe" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "maybe" ? "undo" : "maybe")}
            aria-pressed={photo.state === "maybe"}
            aria-label={maybeTip}
            data-tip={`${maybeTip} (M)`}
          >
            {t("btn_maybe")}
            <kbd className="btn-kbd">m</kbd>
          </button>
          <button
            className={`btn btn-del${photo.state === "delete" ? " active" : ""}`}
            onClick={() => onDecide(photo.state === "delete" ? "undo" : "delete")}
            aria-pressed={photo.state === "delete"}
            aria-label={trashTip}
            data-tip={`${trashTip} (X)`}
          >
            {t("btn_trash")}
            <kbd className="btn-kbd">x</kbd>
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => onDecide("undo")}
            disabled={photo.state === "none"}
            aria-label={t("clear_label")}
            data-tip={`${t("clear_label")} (U)`}
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
              {p.suggested && <span className="film-badge">✨</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
