# Photo Cherrypick — Desktop (local-first)

A downloadable photo-culling app for photographers. Point it at a **local folder of RAW/JPEG**,
it scores and groups near-duplicate bursts **offline**, you cull with a keyboard-driven UI, and it
hands the keepers back as the **original files** in sorted folders — ready to edit.

## Download (macOS)

**Photo Cherrypick** is distributed as an unsigned macOS app for **Apple Silicon (arm64) only** —
M1/M2/M3/M4 Macs. It will **not** run on Intel Macs.

- **Primary download — itch.io:** **https://michaelpotemkin.itch.io/photo-cherrypick**
  Download `Photo Cherrypick.dmg`, open it, and drag **Photo Cherrypick** into **Applications**.
- **Also on GitHub Releases:** **https://github.com/MichaelPotemkin/photo-cherrypick-desktop/releases/latest**
  (the `.dmg` is attached to each release; GitHub Releases is also the source for in-app updates).

### First launch: approve it once (no Terminal)

The app is **not signed with an Apple Developer ID**, so the **first** time you open it macOS asks
you to confirm — expected for an unsigned app. You approve it **once**, with no Terminal commands:

- **Right-click** (or Control-click) **Photo Cherrypick** in Applications → **Open** → **Open**, **or**
- if macOS only offers a **"Done"** button (macOS 15 Sequoia and later): open
  **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to Photo
  Cherrypick, then open it again.

That's it — the app takes care of the rest itself (it clears its own quarantine so the bundled
engine starts; you don't need any `xattr` command). macOS remembers the approval, so subsequent
launches are a normal double-click.

### First launch is slow — and needs internet once

- **First open takes a while (tens of seconds).** The app bundles its Python image-analysis engine
  (PyTorch + OpenCV) as a single frozen binary, which **self-extracts on first run**. Subsequent
  launches are fast. Don't force-quit it during the first launch — let it finish.
- **One-time internet access required.** On first analysis, the app **downloads the ML model
  weights** (CLIP, etc.) to a local cache. After that it runs **fully offline** — your photos never
  leave your Mac.
- **It's a large app (~1–2 GB).** Bundling the full ML stack makes the download and on-disk
  footprint large; this is normal.

### Updates

After the first install, **Photo Cherrypick updates itself**. It checks GitHub Releases on launch
and, when a newer version is available, downloads and installs the update **in place** (the same way
the Claude desktop app updates) — you don't need to revisit itch.io or GitHub to stay current.

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
