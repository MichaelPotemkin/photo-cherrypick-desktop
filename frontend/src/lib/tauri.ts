// Thin bridge to the Tauri runtime. In a browser (vite dev / no shell) these no-op so the user
// can paste a path manually; inside the packaged Tauri app they invoke the native folder dialog.

interface TauriDialog {
  open?: (opts: { directory?: boolean; multiple?: boolean }) => Promise<string | string[] | null>;
}
interface TauriEvent {
  listen?: <T>(
    event: string,
    handler: (e: { payload: T }) => void,
  ) => Promise<() => void>;
  emit?: (event: string, payload?: unknown) => Promise<void>;
}
interface TauriApp {
  getVersion?: () => Promise<string>;
}
interface TauriGlobal {
  dialog?: TauriDialog;
  event?: TauriEvent;
  app?: TauriApp;
}

function tauri(): TauriGlobal | undefined {
  return (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__;
}

export function inTauri(): boolean {
  return tauri() !== undefined;
}

// The running app's version (from tauri.conf.json), or null outside the packaged app.
export async function getAppVersion(): Promise<string | null> {
  const t = tauri();
  if (!t?.app?.getVersion) return null;
  try {
    return await t.app.getVersion();
  } catch {
    return null;
  }
}

// Subscribe to a Tauri event from the SPA. Returns an unlisten fn (a no-op outside Tauri / on error),
// so callers can always call it in cleanup.
export async function listenEvent<T>(
  name: string,
  cb: (payload: T) => void,
): Promise<() => void> {
  const t = tauri();
  if (!t?.event?.listen) return () => {};
  try {
    return await t.event.listen<T>(name, (e) => cb(e.payload));
  } catch {
    return () => {};
  }
}

// Emit a Tauri event from the SPA (e.g. asking the Rust shell to relaunch). No-op outside Tauri.
export async function emitEvent(name: string, payload?: unknown): Promise<void> {
  const t = tauri();
  if (!t?.event?.emit) return;
  try {
    await t.event.emit(name, payload);
  } catch {
    // ignore
  }
}

export async function pickFolder(): Promise<string | null> {
  const t = tauri();
  if (!t?.dialog?.open) return null;
  try {
    const selected = await t.dialog.open({ directory: true, multiple: false });
    return typeof selected === "string" ? selected : null;
  } catch {
    return null;
  }
}
