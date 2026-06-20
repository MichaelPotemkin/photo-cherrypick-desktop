// Typed fetch helpers + shared types for the local desktop culling backend.
//
// The backend is a local sidecar (FastAPI on 127.0.0.1). When the SPA is served by that sidecar
// (packaged app) API_BASE is same-origin (""); in `vite dev` set VITE_API_BASE=http://localhost:8756.
// No auth token is required locally; the header is sent for compatibility and ignored server-side.
// Image URLs (preview_url / original_url) are local endpoints served from disk.

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

export const API_TOKEN: string =
  import.meta.env.VITE_API_TOKEN ?? "local";

// ---------------------------------------------------------------------------
// Types (mirror the backend contract)
// ---------------------------------------------------------------------------

export type PhotoState = "none" | "favorite" | "maybe" | "delete";
export type DecisionAction = "favorite" | "maybe" | "delete" | "undo";
export type SessionStatus = "pending" | "processing" | "ready" | "error";
// Two ways to group: "burst" = near-duplicate frames shot in quick succession (first culling
// pass); "scene" = all similar shots of the same look/outfit, ignoring time (second pass — build
// a gallery/Instagram set from the keepers).
export type GroupMode = "burst" | "scene";
// The header offers a third view, "feed": the planned gallery arrangement of the favorites.
export type ViewMode = GroupMode | "feed";

export interface Counts {
  none: number;
  favorite: number;
  maybe: number;
  delete: number;
}

export interface PhotoCats {
  focus: number;
  exposure: number;
  subject: number;
  composition: number;
  color: number;
  aesthetic: number;
}

export interface Photo {
  id: string;
  filename: string;
  when: string;
  suggested: boolean;
  overall: number; // 0..1
  reasons: string[];
  axes: Record<string, number>; // 0..1, 13 axes
  cats: PhotoCats; // 0..1 each
  is_bw: boolean;
  state: PhotoState;
  preview_url: string;
  original_url: string;
}

export interface Group {
  idx: number;
  label: string;
  when: string;
  avg_score: number;
  close_call?: boolean; // top-2 frames within a hair — algo isn't confident, human should decide
  photos: Photo[];
}

export interface SessionSummary {
  id: string;
  title: string;
  status: SessionStatus;
  n_total: number;
  counts: Counts;
}

export interface GroupsResponse {
  session: SessionSummary;
  groups: Group[];
}

export interface SessionDetail {
  id: string;
  title: string;
  source_url: string;
  status: SessionStatus;
  n_total: number;
  n_done: number;
  error: string | null;
  counts: Counts;
}

export interface CreateSessionResponse {
  id: string;
  title: string;
  n_total: number;
  status: string;
}

export interface DecisionResponse {
  state: PhotoState;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

function authHeaders(extra?: Record<string, string>): HeadersInit {
  return {
    "X-API-Token": API_TOKEN,
    ...extra,
  };
}

async function parseError(res: Response): Promise<string> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      detail = String((body as { detail: unknown }).detail);
    }
  } catch {
    // ignore — keep status line
  }
  return detail;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// API endpoints
// ---------------------------------------------------------------------------

// Create a session from a LOCAL FOLDER path (the desktop pivot — no URL upload).
export async function createSession(
  path: string,
): Promise<CreateSessionResponse> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as CreateSessionResponse;
}

export interface SessionListItem {
  id: string;
  title: string | null;
  source_url: string;
  status: SessionStatus;
  n_total: number;
  n_done: number;
  created_at: string | null;
  counts: Counts;
}

export function listSessions(): Promise<SessionListItem[]> {
  return getJson<SessionListItem[]>(`/api/sessions`);
}

export function getSession(id: string): Promise<SessionDetail> {
  return getJson<SessionDetail>(`/api/sessions/${id}`);
}

export function getGroups(
  id: string,
  mode: GroupMode = "burst",
): Promise<GroupsResponse> {
  return getJson<GroupsResponse>(`/api/sessions/${id}/groups?mode=${mode}`);
}

export type ShotScale = "close" | "medium" | "wide";
export interface FeedPhoto extends Photo {
  scale: ShotScale; // close-up / medium / wide(+environmental)
  slot: number; // 1-based position in the planned feed
}
export interface FeedResponse {
  session: SessionSummary;
  photos: FeedPhoto[];
}

export function getFeed(id: string): Promise<FeedResponse> {
  return getJson<FeedResponse>(`/api/sessions/${id}/feed`);
}

export async function renameSession(
  id: string,
  title: string,
): Promise<{ id: string; title: string }> {
  const res = await fetch(`${API_BASE}/api/sessions/${id}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as { id: string; title: string };
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export interface AcceptResponse {
  accepted: number;
  counts: Counts;
}

// Favorite every still-undecided suggested (best-of-burst) pick in one shot.
export async function acceptSuggestions(id: string): Promise<AcceptResponse> {
  const res = await fetch(`${API_BASE}/api/sessions/${id}/accept-suggestions`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as AcceptResponse;
}

export async function postDecision(
  photoId: string,
  action: DecisionAction,
): Promise<DecisionResponse> {
  const res = await fetch(`${API_BASE}/api/photos/${photoId}/decision`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as DecisionResponse;
}

// Direct export URL (token in query so a plain download link can authenticate). The ZIP
// can be large (full-res originals); a direct link lets the browser stream it to disk
// instead of buffering it in memory. The server sets Content-Disposition for the filename.
export function exportUrl(sessionId: string, format: "zip" = "zip"): string {
  return `${API_BASE}/api/sessions/${sessionId}/export?format=${format}&token=${encodeURIComponent(API_TOKEN)}`;
}

export function downloadExport(sessionId: string, format: "zip" = "zip"): void {
  const a = document.createElement("a");
  a.href = exportUrl(sessionId, format);
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
