import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

// A small confirm dialog rendered as a centered overlay. Mirrors HelpModal's focus trap and, crucially,
// swallows every key in the capture phase so the cull-grid shortcuts (f / m / x, arrows, a, n…) can't
// reach the grid behind it. Esc cancels; Tab is trapped; Enter activates the focused primary button
// natively. Clicking the backdrop cancels.
//
// Rendered through a portal to <body>: the sticky header's `backdrop-filter` establishes a containing
// block for fixed-position descendants, which would otherwise trap this overlay inside the header box.
interface Props {
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  title?: string;
  // Destructive confirms (e.g. deleting a session) get a red confirm button and open with focus on
  // Cancel — so a reflexive Enter dismisses rather than performs the irreversible action.
  danger?: boolean;
}

export default function ConfirmModal({
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  title,
  danger = false,
}: Props) {
  const modalRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const messageId = useId();
  // Keep the latest onCancel without re-running the mount effect (which would re-steal focus on every
  // parent re-render, e.g. a background counts refetch).
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    // Open with focus on the safe action for destructive confirms, otherwise on the primary action.
    (danger ? cancelBtnRef : confirmRef).current?.focus();

    const focusables = (): HTMLElement[] =>
      Array.from(
        modalRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));

    const onKey = (e: KeyboardEvent) => {
      e.stopPropagation();
      if (e.key === "Escape") {
        e.preventDefault();
        cancelRef.current();
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

  return createPortal(
    <div className="modal-overlay" onClick={() => onCancel()}>
      <div
        className="modal confirm-modal"
        role="dialog"
        aria-modal="true"
        // Name the dialog by its title when present, otherwise by the message node itself (not a second
        // copy of the string) so screen readers don't announce the same sentence twice.
        aria-labelledby={title ? titleId : messageId}
        aria-describedby={title ? messageId : undefined}
        tabIndex={-1}
        ref={modalRef}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <h2 id={titleId} className="confirm-title">
            {title}
          </h2>
        )}
        <p id={messageId} className="confirm-message">
          {message}
        </p>
        <div className="confirm-actions">
          <button className="btn btn-ghost" ref={cancelBtnRef} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={`btn ${danger ? "btn-danger" : "btn-accent"}`}
            ref={confirmRef}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
