import { useEffect, useState } from "react";
import { emitEvent, getAppVersion, inTauri, listenEvent } from "./lib/tauri";

// Drives the in-app auto-update UI (see UpdateFooter). The Rust shell checks + downloads the update in
// the background and reports progress over Tauri events; this hook turns those into a small state
// machine and exposes a relaunch trigger. Outside the packaged app (browser / vite dev) it stays idle.
export type UpdateStage = "idle" | "downloading" | "ready" | "error";

export interface UpdaterState {
  version: string | null; // running app version, for the bottom-of-screen label
  stage: UpdateStage;
  percent: number | null; // null while the total size is unknown (indeterminate bar)
  newVersion: string | null; // version being installed
}

const INITIAL: UpdaterState = { version: null, stage: "idle", percent: null, newVersion: null };

export function useUpdater(): UpdaterState & { relaunch: () => void } {
  const [state, setState] = useState<UpdaterState>(INITIAL);

  useEffect(() => {
    if (!inTauri()) return;
    let cancelled = false;
    const unlisteners: Array<() => void> = [];

    (async () => {
      const version = await getAppVersion();
      if (!cancelled) setState((s) => ({ ...s, version }));

      const subs = await Promise.all([
        listenEvent<{ version: string }>("update-available", (p) =>
          setState((s) => ({ ...s, stage: "downloading", percent: null, newVersion: p.version })),
        ),
        listenEvent<{ downloaded: number; total: number | null }>("update-progress", (p) =>
          setState((s) => ({
            ...s,
            stage: "downloading",
            percent: p.total ? Math.min(100, Math.round((p.downloaded / p.total) * 100)) : null,
          })),
        ),
        listenEvent<{ version: string }>("update-ready", (p) =>
          setState((s) => ({ ...s, stage: "ready", percent: 100, newVersion: p.version })),
        ),
        listenEvent<{ message: string }>("update-error", () =>
          // fall back to just showing the version label; a failed background update isn't worth a
          // disruptive in-app error — the next launch retries.
          setState((s) => ({ ...s, stage: "idle", percent: null })),
        ),
      ]);

      if (cancelled) {
        subs.forEach((u) => u());
      } else {
        unlisteners.push(...subs);
        // Tell the Rust shell we're subscribed; it replays the latest update state, covering a
        // download that finished before this webview existed (cold start).
        void emitEvent("spa-ready");
      }
    })();

    return () => {
      cancelled = true;
      unlisteners.forEach((u) => u());
    };
  }, []);

  const relaunch = () => {
    void emitEvent("update-relaunch");
  };

  return { ...state, relaunch };
}
