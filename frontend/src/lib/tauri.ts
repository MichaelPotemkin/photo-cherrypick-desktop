// Thin bridge to the Tauri runtime. In a browser (vite dev / no shell) these no-op so the user
// can paste a path manually; inside the packaged Tauri app they invoke the native folder dialog.

interface TauriDialog {
  open?: (opts: { directory?: boolean; multiple?: boolean }) => Promise<string | string[] | null>;
}
interface TauriGlobal {
  dialog?: TauriDialog;
}

function tauri(): TauriGlobal | undefined {
  return (window as unknown as { __TAURI__?: TauriGlobal }).__TAURI__;
}

export function inTauri(): boolean {
  return tauri() !== undefined;
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
