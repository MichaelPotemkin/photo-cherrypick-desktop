# Phase 1 — Implementation Report (Desktop / local-first culler)

**Goal:** implement Phase 1 of the desktop pivot — a local-first Mac culling app — in a dedicated
repo; plan, implement, evaluate. **Status: functional core implemented and verified.** The Tauri
packaging shell is scaffolded (needs Rust to compile; same backend runs standalone today).

## What Phase 1 was (from the PRD)
7 P0 must-haves: macOS desktop shell · open a **local folder** · **RAW preview-first** · **non-destructive**
catalog · **export mapped back to originals** · **assist-don't-decide** · **show-everything + compare**.

## What was built

| PRD item | Status | Where |
|---|---|---|
| A1 macOS desktop shell | **Scaffold** (Tauri v2; needs `rustup` to build) | `desktop/` |
| A2 open a local folder | **Done** | `desktop_core/ingest.py`, `POST /api/sessions {path}` |
| A3 RAW preview-first | **Done** (embedded JPEG → full decode → graceful "unsupported") | `desktop_core/raw_preview.py` |
| A4 non-destructive catalog | **Done** (SQLite references files in place; nothing moved without explicit action) | `desktop_core/store.py` |
| A5 export mapped to originals | **Done** (sorted folders + report.csv, copy by default) | `desktop_core/export.py` |
| B1 assist-don't-decide | **Done** (picks are suggestions; nothing auto-deleted/hidden) | `pipeline_runner.py` + SPA |
| B4 show everything + compare | **Done** (reused SPA grid/lightbox/keyboard, source-agnostic) | `frontend/` |

**Reuse:** the entire `pipeline/` analysis core (torch + open_clip + OpenCV scoring, burst grouping,
suggestion logic) is reused **verbatim** from the hosted app — same outputs. Only the I/O changed:
local files instead of a CDN, SQLite instead of Postgres+pgvector, a local folder instead of a
Gallera URL. The React SPA is reused too; only the entry screen swapped to a folder picker.

**Architecture:** Tauri shell → spawns a Python sidecar (`server.app`, FastAPI on 127.0.0.1) →
serves the built SPA + API + images from disk. Decided per your call: Tauri + reuse, not a native
rewrite.

## How it was evaluated

1. **Hermetic test suite — 24/24 pass** (`pytest`), no model downloads:
   - `raw_preview` (format dispatch, JPEG/PNG load, graceful None on a non-RAW `.nef`, thumbnail bounds)
   - `ingest` (RAW+JPEG pairing, recursion, hidden/non-image filtering, ordering)
   - `store` (session CRUD, **latest-decision-wins** state, counts, analysis round-trip, FK cascade)
   - `grouping` (real pure-numpy `pipeline.score`/`group`: unit-range scores, faceless ≤0.5 cap,
     similarity+time burst grouping, pose-change split)
   - `pipeline_runner` (full orchestration with a scripted analyze: bursts, suggestion sort,
     **blink demotion**, one-suggested-per-burst, cache files written)
   - `server` (FastAPI TestClient e2e: create→ready→groups→decision→counts→image→zip/csv→rename→delete)

2. **Real ML pipeline, end-to-end via CLI** on a 15-image synthetic shoot:
   `analyzed 15 in 0.9s (0.06s/photo)`, real CLIP + face detection, the 3 designed near-duplicate
   bursts each grouped as 3-frame bursts, faceless frames scored ≤0.5 (matches the contract),
   suggested picks set, export copied 7 keepers to `favorites/` + `report.csv`, **originals
   untouched** (non-destructive confirmed).

3. **Live full-stack smoke** (real `uvicorn server.app` serving the **built SPA** + API):
   `POST /api/sessions {path}` → `status: ready` (15 photos) → 7 groups → favorite → counts update →
   `/api/img/{id}/preview` 200 image/jpeg → `/` serves the SPA (`<title>Photo Cherrypick</title>`) →
   `export?format=zip` 200 (23 KB). Frontend builds clean (`tsc -b && vite build`, 0 type errors).
   Re-run in **threaded (background-worker) mode**: pending→processing→ready on a per-thread
   connection with a concurrent decision write — no errors; export left no temp leak; a cross-origin
   request from `evil.com` received no `Access-Control-Allow-Origin`.

## Adversarial review & fixes

A multi-agent review (4 reviewers × independent skeptic verification) audited the new code against
the reuse contracts. It confirmed **5 real bugs**, all fixed and regression-tested:

| # | Sev | Bug | Fix |
|---|-----|-----|-----|
| 1 | High | One shared SQLite connection across the worker + request threads (no locking) → reproduced lost decisions + `API misuse` errors | Per-thread connections + WAL + `busy_timeout`; new concurrency test (8 writers + readers, 0 loss) |
| 2 | High | Embedded RAW preview not EXIF-transposed → portrait RAWs analyzed/shown sideways | `exif_transpose` the embedded JPEG; new orientation test (8×4→4×8) |
| 3 | Med | Export zip temp file leaked (no cleanup task; also on exception) | `BackgroundTask` unlink + `try/except` unlink |
| 4 | Med | `CORS allow_origins=['*']` on a no-auth local server → local-CSRF/exfil | Scoped to localhost/Tauri origins (SPA is same-origin anyway) |
| 5 | Med | Hidden-file filter checked only the leaf name → ingested `.Trashes`/`.Spotlight-V100` contents | Skip any path with a hidden component |

## Known limitations / honest gaps
- **Tauri app not compiled** here (no Rust toolchain in the environment). The shell is a correct v2
  scaffold; the backend it wraps is fully working and runnable standalone today.
- **No real RAW file was tested** — only the dispatch/fallback logic is unit-tested. Preview-first
  needs QA on real camera files (exactly the PRD's "get sample RAWs" ask). RAW EXIF (capture time)
  may be thin when read from an embedded preview, degrading time-based grouping (similarity still
  groups); JPEG sidecars are preferred for EXIF.
- **No real photographer photos** evaluated — synthetic images have no faces, so face/expression
  axes weren't exercised end-to-end (the hosted app already validated those on real shoots).
- Deferred by design: editor-specific export adapters (XMP/Lightroom/Capture One), feed-layout
  planner, localization, Windows, ONNX bundle slimming.
- **No SQLite schema migrations** — the store uses `CREATE TABLE IF NOT EXISTS`, so a DB created by
  an older build is NOT upgraded when columns change (surfaced live in Preview: an old `cull.db`
  with the pre-rename `path` column caused an insert error until the stale data dir was deleted).
  Fine pre-release (no real user data; just delete `~/.photo-cherrypick-desktop`), but **Phase 2
  needs a lightweight migration / schema-version mechanism** before any real user has a DB worth keeping.

## Running in Preview
`.claude/launch.json` has a `desktop` config (`python -m server.run --port 8756`) — `preview_start`
launches the FastAPI sidecar serving the SPA + API same-origin. Verified live: SPA loads, API calls
resolve same-origin, and a 10-image sample shoot ran folder→analyze→ready (3 groups) with the cull
grid + disk-served images rendering. (Build fix found here: a copied `.env` had baked
`VITE_API_BASE=http://localhost:8000` into the bundle → set empty for same-origin and rebuilt.)

## Code
~1,650 LOC new (`desktop_core/` + `server/` + `tests/`) + reused `pipeline/` and `frontend/`.
Not committed (no commit was requested) — `git init`'d, ready for an initial commit on a branch.

## Suggested next steps
1. **Get sample RAWs from Anastasiya** and QA preview-first rendering/orientation on real camera files.
2. **Compile the Tauri shell** (`rustup` + PyInstaller sidecar) → first real `.app`/`.dmg`; sign + notarize.
3. **Design-partner test** (PRD M5): real shoot end-to-end; measure recall of her keepers + reasons for rejects — the first real data on our judgment quality.
4. Then Phase 2: editor-specific export adapters, localization, perf; Phase 3: feed-layout planner, Windows.
