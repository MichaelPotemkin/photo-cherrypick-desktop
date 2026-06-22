import { downloadExport, exportCheck, type ExportFormat } from "../api";

// Pre-flight an export before triggering the download. If NONE of the selected originals are still on
// disk — the source folder was moved, renamed, or deleted after culling — show `noneFoundMessage`
// instead of letting the browser download a misleading empty zip (the bug that looked like a broken
// export). Otherwise fall through to the streaming direct-link download. A failed check never blocks
// the download — we'd rather attempt it than swallow a transient hiccup.
export async function exportWithCheck(
  sessionId: string,
  format: ExportFormat,
  noneFoundMessage: string,
): Promise<void> {
  try {
    const { found } = await exportCheck(sessionId, format);
    if (found === 0) {
      window.alert(noneFoundMessage);
      return;
    }
  } catch {
    // check failed (offline / server hiccup) — don't block; the direct download still works
  }
  downloadExport(sessionId, format);
}
