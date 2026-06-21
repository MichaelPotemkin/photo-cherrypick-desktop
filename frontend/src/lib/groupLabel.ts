import type { ViewMode } from "../api";

type TFn = (key: string, vars?: Record<string, string | number>) => string;

// Localized group label ("N in burst — pick one" / "single shot", or the scene equivalents), rebuilt
// client-side so it localizes. Shared by GroupGrid and Lightbox so the wording can't drift between them.
export function buildGroupLabel(t: TFn, mode: ViewMode, n: number): string {
  if (mode === "scene") return n > 1 ? t("label_scene", { n }) : t("label_unique");
  return n > 1 ? t("label_burst_pick", { n }) : t("label_single");
}
