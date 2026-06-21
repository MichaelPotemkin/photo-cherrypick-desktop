import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useKeyboard, type ClosedHandlers, type OpenHandlers } from "./useKeyboard";

const CLOSED_KEYS = [
  "onLeft", "onRight", "onPrevGroup", "onNextGroup", "onFavorite", "onMaybe",
  "onDelete", "onUndo", "onAcceptSuggestion", "onNextUndecided", "onOpen", "onToggleHide",
] as const;
const OPEN_KEYS = [
  "onLeft", "onRight", "onPrevGroup", "onNextGroup", "onFavorite", "onMaybe",
  "onDelete", "onUndo", "onClose",
] as const;

const makeClosed = () =>
  Object.fromEntries(CLOSED_KEYS.map((k) => [k, vi.fn()])) as unknown as ClosedHandlers;
const makeOpen = () =>
  Object.fromEntries(OPEN_KEYS.map((k) => [k, vi.fn()])) as unknown as OpenHandlers;

function press(key: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

describe("useKeyboard — grid (lightbox closed)", () => {
  it("routes every grid shortcut to its handler", () => {
    const closed = makeClosed();
    const open = makeOpen();
    renderHook(() => useKeyboard({ lightboxOpen: false, closed, open }));

    const cases: [string, keyof ClosedHandlers][] = [
      ["ArrowLeft", "onLeft"], ["ArrowRight", "onRight"], ["ArrowUp", "onPrevGroup"],
      ["ArrowDown", "onNextGroup"], ["f", "onFavorite"], ["m", "onMaybe"], ["x", "onDelete"],
      ["u", "onUndo"], ["a", "onAcceptSuggestion"], ["n", "onNextUndecided"], ["Enter", "onOpen"],
      ["h", "onToggleHide"],
    ];
    for (const [key, handler] of cases) {
      press(key);
      expect(closed[handler], `key "${key}" -> ${handler}`).toHaveBeenCalledOnce();
    }
    expect(open.onClose).not.toHaveBeenCalled(); // lightbox-only handler never fired
  });

  it("treats uppercase the same (Shift held)", () => {
    const closed = makeClosed();
    renderHook(() => useKeyboard({ lightboxOpen: false, closed, open: makeOpen() }));
    press("F");
    press("X");
    expect(closed.onFavorite).toHaveBeenCalledOnce();
    expect(closed.onDelete).toHaveBeenCalledOnce();
  });
});

describe("useKeyboard — lightbox open", () => {
  it("routes to the open handlers, incl. Escape -> onClose and Delete -> onDelete", () => {
    const closed = makeClosed();
    const open = makeOpen();
    renderHook(() => useKeyboard({ lightboxOpen: true, closed, open }));
    press("ArrowRight");
    press("Escape");
    press("Delete");
    expect(open.onRight).toHaveBeenCalledOnce();
    expect(open.onClose).toHaveBeenCalledOnce();
    expect(open.onDelete).toHaveBeenCalledOnce();
    press("a"); // grid-only shortcut is inert in the lightbox
    expect(closed.onAcceptSuggestion).not.toHaveBeenCalled();
  });
});

describe("useKeyboard — guards", () => {
  it("does nothing when active=false", () => {
    const closed = makeClosed();
    renderHook(() => useKeyboard({ lightboxOpen: false, closed, open: makeOpen(), active: false }));
    press("f");
    expect(closed.onFavorite).not.toHaveBeenCalled();
  });

  it("ignores shortcuts while typing in an input", () => {
    const closed = makeClosed();
    renderHook(() => useKeyboard({ lightboxOpen: false, closed, open: makeOpen() }));
    const input = document.createElement("input");
    document.body.appendChild(input);
    press("f", input);
    expect(closed.onFavorite).not.toHaveBeenCalled();
    input.remove();
  });
});
