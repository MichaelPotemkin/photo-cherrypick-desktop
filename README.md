# Photo Cherrypick — Desktop (local-first)

A downloadable photo-culling app for photographers. Point it at a **local folder of RAW/JPEG**,
it scores and groups near-duplicate bursts **offline**, you cull with a keyboard-driven UI, and it
hands the keepers back as the **original files** in sorted folders — ready to edit.

This is the Phase-1 pivot from the hosted web app (paste a Gallera URL → cull → download). See
[`docs/PHASE1-REPORT.md`](docs/PHASE1-REPORT.md) for what's built and verified, and the PRD in the
sibling `photo-cherrypick` repo (`docs/prd/phase1-mac-mvp.md`).

## Why local-first

Pros shoot/store RAW on disk and cull by eye. The web flow forced RAW→JPEG→upload to a per-GB
gallery→analyze→re-find originals — a backwards, costly round-trip. This app removes it: nothing
is uploaded, decisions map straight back to the originals.

## Architecture

```
desktop/        Tauri v2 shell (M1 scaffold) — spawns the sidecar, native folder dialog
server/         FastAPI local server (127.0.0.1): SPA + API + image serving from disk
desktop_core/   the new local logic:
  raw_preview.py   preview-first RAW loading (embedded JPEG → full decode → graceful unsupported)
  ingest.py        scan a folder, pair RAW+JPEG
  store.py         SQLite store (sessions/photos/analyses/groups/append-only decisions)
  pipeline_runner.py  orchestration (analyze → refs → burst groups → suggestion sort → persist)
  export.py        copy/zip keepers as the original files, FLAT (non-destructive)
  feed.py          feed-layout planner (arrange favorites into a balanced IG/gallery grid)
  views.py         read-models for the SPA (burst / scene grouping + feed)
  cli.py           headless culling + eval harness
pipeline/       the analysis core, REUSED from the hosted app (torch + open_clip + OpenCV),
                extended for multi-face/group scoring
frontend/       the React/Vite/TS SPA: cull grid, lightbox, scene + feed views, EN/UK i18n
tests/          hermetic pytest suite (no model downloads)
```

## Workflow & views

- **Burst** — the first cull pass: near-duplicate frames grouped into bursts; pick the keeper from
  each (the algorithm suggests one; **Accept picks** bulk-favorites all suggestions).
- **Scene** — the second pass: keepers re-grouped by look (same setting/outfit) via mean-centered
  CLIP clustering, for assembling a gallery set.
- **Feed** — arrange the favorites into a balanced 3-wide Instagram/gallery grid (alternating shot
  scale, scenes spread out).
- UI is keyboard-driven (`f`/`m`/`x`/`u`, arrows, `a`, `n`, `h`) and localized **English / Ukrainian**.

The cull engine (`pipeline/`) is unchanged from the hosted product — same scoring, grouping, and
suggestion logic. Only the I/O around it is new (local files + SQLite instead of CDN + Postgres).

## Run it today (no Tauri / no Rust needed)

```bash
pip install torch==2.12.0 torchvision==0.27.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..      # builds the SPA the server serves

python -m server.run --port 8756                          # then open http://127.0.0.1:8756
```

Or headless / for evaluation:

```bash
python -m desktop_core.cli cull /path/to/shoot --export /path/to/picks
```

## Test

```bash
pytest -q          # hermetic tests (ingest, RAW preview, store/migrations, scoring, grouping,
                   # scene clustering, feed planner, run_session, full API e2e) + `cd frontend && npx vitest run`
```

## Status

Functional core **implemented + verified**: local-folder ingest, preview-first RAW (incl. CR3/CR2),
multi-axis scoring with multi-face/group support, burst + scene grouping, the feed planner, flat
export, EN/UK localization, and self-healing SQLite migrations. The Tauri packaging shell is a
scaffold (needs `rustup` to compile — see `desktop/README.md`).

Known limitations and planned work are tracked in **[GitHub issues](../../issues)**. Highlights:
editor-specific export adapters (XMP/Lightroom/Capture One), feed v2 (manual reorder / export-as-grid),
improving family/group pick quality (detection recall is the lever), and validating picks against the
photographer's real selections.
