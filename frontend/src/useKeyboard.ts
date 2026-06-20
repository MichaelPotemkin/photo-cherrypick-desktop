import { useEffect } from "react";

// Returns true if the event target is a text input / editable element, in which
// case global shortcuts should be ignored.
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return target.isContentEditable;
}

export interface ClosedHandlers {
  onLeft: () => void;
  onRight: () => void;
  onPrevGroup: () => void;
  onNextGroup: () => void;
  onFavorite: () => void;
  onMaybe: () => void;
  onDelete: () => void;
  onUndo: () => void;
  onAcceptSuggestion: () => void;
  onNextUndecided: () => void;
  onOpen: () => void;
  onToggleHide: () => void;
}

export interface OpenHandlers {
  onLeft: () => void;
  onRight: () => void;
  onPrevGroup: () => void;
  onNextGroup: () => void;
  onFavorite: () => void;
  onMaybe: () => void;
  onDelete: () => void;
  onUndo: () => void;
  onClose: () => void;
}

interface Args {
  lightboxOpen: boolean;
  closed: ClosedHandlers;
  open: OpenHandlers;
  active?: boolean; // false disables all shortcuts (e.g. in the read-only feed view)
}

export function useKeyboard({ lightboxOpen, closed, open, active = true }: Args) {
  useEffect(() => {
    if (!active) return;
    function handler(e: KeyboardEvent) {
      if (isTypingTarget(e.target)) return;

      if (lightboxOpen) {
        switch (e.key) {
          case "ArrowLeft":
            e.preventDefault();
            open.onLeft();
            break;
          case "ArrowRight":
            e.preventDefault();
            open.onRight();
            break;
          case "ArrowUp":
            e.preventDefault();
            open.onPrevGroup();
            break;
          case "ArrowDown":
            e.preventDefault();
            open.onNextGroup();
            break;
          case "f":
          case "F":
            open.onFavorite();
            break;
          case "m":
          case "M":
            open.onMaybe();
            break;
          case "x":
          case "X":
          case "Delete":
            open.onDelete();
            break;
          case "u":
          case "U":
            open.onUndo();
            break;
          case "Escape":
            e.preventDefault();
            open.onClose();
            break;
          default:
            break;
        }
        return;
      }

      // Lightbox closed.
      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          closed.onLeft();
          break;
        case "ArrowRight":
          e.preventDefault();
          closed.onRight();
          break;
        case "ArrowUp":
          e.preventDefault();
          closed.onPrevGroup();
          break;
        case "ArrowDown":
          e.preventDefault();
          closed.onNextGroup();
          break;
        case "f":
        case "F":
          closed.onFavorite();
          break;
        case "m":
        case "M":
          closed.onMaybe();
          break;
        case "x":
        case "X":
        case "Delete":
          closed.onDelete();
          break;
        case "u":
        case "U":
          closed.onUndo();
          break;
        case "a":
        case "A":
          closed.onAcceptSuggestion();
          break;
        case "n":
        case "N":
          closed.onNextUndecided();
          break;
        case "Enter":
          e.preventDefault();
          closed.onOpen();
          break;
        case "h":
        case "H":
          closed.onToggleHide();
          break;
        default:
          break;
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightboxOpen, closed, open, active]);
}
