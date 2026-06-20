import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n, tVariants } from "../i18n";
import StableLabel from "./StableLabel";

// The how-to guide for the cull → scene → feed workflow. Three shapes share one set of strings:
//   <HelpContent/> — the steps body, embedded inline on the loading screen,
//   <HelpModal/>   — a dismissible overlay,
//   <HelpButton/>  — a self-contained trigger that owns the modal's open state.

const PASSES = ["pass1", "pass2", "pass3"] as const;

export function HelpContent() {
  const { t } = useI18n();
  return (
    <div className="help-content">
      <p className="help-intro">{t("help_intro")}</p>
      <ol className="help-steps">
        {PASSES.map((p) => (
          <li key={p} className="help-step">
            <span className="help-step-title">{t(`help_${p}_title`)}</span>
            <span className="help-step-body">{t(`help_${p}_body`)}</span>
          </li>
        ))}
      </ol>
      <p className="help-download muted">{t("help_download")}</p>
    </div>
  );
}

export function HelpModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const modalRef = useRef<HTMLDivElement>(null);
  // Keep the latest onClose without re-running the mount effect — onClose gets a new identity on every
  // HelpButton render (e.g. when the language changes while the modal is open), which would otherwise
  // re-steal focus back into the dialog.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    modalRef.current?.focus(); // move focus into the dialog on open

    const focusables = (): HTMLElement[] =>
      Array.from(
        modalRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));

    // Capture phase + stopPropagation so this swallows every key before the session's window
    // keydown handler (bubble phase) — otherwise f/m/x, arrows, a, n etc. would mutate the cull
    // grid hidden behind the overlay. Esc closes; Tab is trapped inside the dialog.
    const onKey = (e: KeyboardEvent) => {
      e.stopPropagation();
      if (e.key === "Escape") {
        e.preventDefault();
        closeRef.current();
      } else if (e.key === "Tab") {
        const items = focusables();
        if (items.length === 0) {
          e.preventDefault();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        const act = document.activeElement;
        if (e.shiftKey && (act === first || act === modalRef.current)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && act === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      prevFocus?.focus?.(); // restore focus to the trigger on close
    };
  }, []);

  // Portal to <body>: the sticky header's `backdrop-filter` would otherwise trap this fixed overlay
  // inside the header box (it establishes a containing block for fixed-position descendants).
  return createPortal(
    <div className="help-overlay" onClick={onClose}>
      <div
        className="help-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("help_title")}
        tabIndex={-1}
        ref={modalRef}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="help-close" onClick={onClose} aria-label={t("close")}>
          ✕
        </button>
        <h2 className="help-modal-title">{t("help_title")}</h2>
        <HelpContent />
        <div className="help-actions">
          <button className="btn btn-accent" onClick={onClose}>
            {t("help_got_it")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function HelpButton({ className }: { className?: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={`btn btn-ghost help-btn${className ? ` ${className}` : ""}`}
        onClick={() => setOpen(true)}
        data-tip={t("help_title")}
      >
        <StableLabel
          text={`ⓘ ${t("help_button")}`}
          reserve={tVariants("help_button").map((v) => `ⓘ ${v}`)}
        />
      </button>
      {open && <HelpModal onClose={() => setOpen(false)} />}
    </>
  );
}
