# Real end-to-end analyze testing (`CULL_REAL`)

The hermetic pytest suite never runs the torch/OpenCV models. As `tests/conftest.py` puts it:

> The hermetic tests never execute the torch/CV models — they either exercise pure-numpy pipeline
> code (score/group) with hand-built measurement dicts, or monkeypatch `analyze` with a synthetic
> meta. A real end-to-end analyze run is exercised separately (CLI / `CULL_REAL=1`).

This doc explains what that "real" path is, why it's separate, and how to run it locally.

## What `CULL_REAL=1` actually means

**`CULL_REAL` is not an environment variable the code reads.** Grep the repo and the only hit is the
comment above in `tests/conftest.py`. It's a *label* for "run the real ML pipeline end-to-end against
real image files" rather than a flag any branch checks. There is no `os.environ.get("CULL_REAL")`
anywhere, so setting `CULL_REAL=1` on its own changes nothing — you invoke the real path by running
the pipeline against actual images (via the CLI or the server), not by flipping a flag.

The split exists because of how the tests fake analysis:

- `pipeline/analyze.py` `analyze(pil, ctime)` is the real per-photo measurement function. It calls
  `pipeline.embed` / `pipeline.faces` / `pipeline.metrics`, which in turn pull the lazy model
  singletons in `pipeline/models.py` (YuNet face detector, Haar cascades, open_clip ViT-B/32, the
  LAION aesthetic head).
- The hermetic tests (`tests/test_pipeline_runner.py`, `tests/test_server_e2e.py`) replace it with
  `monkeypatch.setattr(pipeline_runner, "analyze", fake_analyze)`, feeding hand-built measurement
  dicts from `tests/conftest.py:make_meta`. Everything *downstream* of `analyze` — `compute_refs`,
  `build_groups`, the suggestion sort + blink penalty, persistence, and the read-models — is the real
  code. Only the torch/CV measurement step is stubbed.

So the hermetic suite proves the orchestration and scoring math are correct; it does **not** prove the
torch/OpenCV measurement step (`analyze`) still works. A torch/torchvision/open_clip/opencv upgrade
that broke `analyze` would pass `pytest -q`. The "real analyze" run is how you catch that.

## Why torch is excluded from the default suite

It isn't excluded for lack of the package — `.github/workflows/ci.yml` actually installs CPU torch
before `pytest -q`. It's excluded because a real run needs things the hermetic suite deliberately
avoids:

- **Network on first run** to download model weights (see below) — CI and `pytest` must stay
  offline/deterministic.
- **Real photographs** with faces/scenes; the synthetic `Image.new(...)` fixtures in `conftest.py`
  have nothing for the face detector or CLIP prompts to measure.
- **Time** — loading the models (`warmup()`) plus running CLIP/YuNet per photo is far slower than the
  numpy-only assertions the hermetic tests rely on.

`pytest -q` is the fast, hermetic, offline gate; the real analyze run is a manual, weights-downloading
pass you do locally against a sample folder.

## Running a real end-to-end analysis locally

### 1. Install the ML deps

Per the top of `requirements.txt`, torch + torchvision come from the CPU wheel index (a matched pair),
then the rest:

```bash
pip install torch==2.12.0 torchvision==0.27.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The packages the real `analyze` path needs are all pinned in `requirements.txt`:
`torch`, `torchvision`, `open_clip_torch`, `opencv-python-headless`, `numpy`, `pillow` (and `rawpy`
for RAW preview-first loading). The hermetic-only extras (`pytest`, `httpx`, `ruff`) aren't required
just to run analysis, but `pip install -r requirements.txt` brings everything.

### 2. Run it — the CLI is the real end-to-end harness

`desktop_core/cli.py` is the headless culler and the primary evaluation harness. It runs the **full
real pipeline** (no mocks): `scan_folder` → `warmup()` → real `analyze` → `compute_refs` →
`build_groups` → suggestion sort → persist, then prints a per-group summary.

```bash
python -m desktop_core.cli cull /path/to/test-images
```

Useful flags (see `cli.py`):

- `--export /path/to/picks` — also copy each group's suggested pick out (exercises the export path).
- `--auto-favorite` — favorite every suggested pick (exercises the decision path) before export.
- `--json out.json` — dump the summary + groups for diffing across runs.
- `--db PATH` / `--cache DIR` — pin the SQLite db / preview cache (default: fresh temp dirs each run).

Point it at a **small folder** (a handful to a couple dozen JPEGs and/or RAWs — ideally with real
faces and a couple of near-duplicate bursts so grouping and the blink/sharpness suggestion logic
actually do something). The CLI prints warmup time and `analyzed N in Xs (Y s/photo)` to stderr.

### 3. Or run it through the server

The server calls the same real `pipeline_runner.run_session` (real `analyze`):

```bash
python -m server.run --port 8756        # then POST a folder to /api/sessions, or open the SPA
```

By default the server analyzes in a background worker thread. Set `CULL_SYNC=1` to process inline
(the same flag the e2e test uses) if you want the `POST /api/sessions` call to block until analysis
finishes:

```bash
CULL_SYNC=1 python -m server.run --port 8756
```

## What to expect

- **First-run model downloads (one-time, needs internet).** `pipeline/models.py` downloads, on first
  use, into the weights dir:
  - **YuNet** face detector — `face_detection_yunet_2023mar.onnx` (from opencv_zoo).
  - **LAION aesthetic head** — `sa_0_4_vit_b_32_linear.pth`.

  Plus **open_clip** downloads the `ViT-B-32-quickgelu` (`pretrained="openai"`) weights into its own
  cache (`~/.cache/...`) the first time `clip()` runs. After these land, subsequent runs are fully
  offline. You'll see `downloading <name> ...` lines on the first run.

  Weights location (from `_weights_dir()`): `pipeline/weights/` when running from source, or
  `$CULL_DATA_DIR/weights` (default `~/.photo-cherrypick-desktop/weights`) when frozen.
  `CULL_WEIGHTS_DIR` overrides either way.

- **Timing.** First run pays the download + `warmup()` cost (loading torch + the models). After warmup,
  per-photo time is dominated by CLIP image/text encoding and YuNet, but it's fast on CPU: the recorded
  real-pipeline run in `docs/PHASE1-REPORT.md` measured `analyzed 15 in 0.9s (0.06s/photo)` on a
  synthetic shoot. The CLI prints warmup time and the actual `s/photo`; even so, use a small folder so a
  full run is seconds, not minutes.

- **Graceful model fallbacks.** If YuNet can't be created it falls back to Haar
  (`pipeline/models.py:yunet()`); if the aesthetic head can't load, `aesthetic_score` returns `None`.
  These are logged, not fatal — a real run still completes, just with degraded signals.

## Relevant environment variables (real ones)

None of these are `CULL_REAL`; they're the actual knobs the real path reads:

- `CULL_DATA_DIR` — app-data root (db, cache, and frozen weights). Default `~/.photo-cherrypick-desktop`.
- `CULL_WEIGHTS_DIR` — override the model-weights download dir.
- `CULL_SYNC=1` — server processes analysis inline instead of on the background worker thread.
- `YUNET_SCORE` — YuNet confidence threshold (default `0.6`); the eval harness sweeps it.
- `TORCH_DEVICE` — force the torch device; otherwise `cuda` if available, else `cpu`.

## Caveats

- **Not run in CI.** `.github/workflows/ci.yml` runs only `pytest -q` (hermetic, faked `analyze`).
  Nothing runs the real `analyze` end-to-end in CI, and the release pipeline
  (`.github/workflows/release-macos.yml`) doesn't either. A torch/open_clip/opencv regression that
  breaks measurement will pass CI — running this real pass locally before a dependency bump or a
  release is the only guard. (One such real run is recorded in `docs/PHASE1-REPORT.md` under
  "Real ML pipeline, end-to-end via CLI".)
- **Single-threaded.** The `pipeline/` model singletons are not thread-safe; `run_session` analyzes
  sequentially and `warmup()` must run once before processing. Don't parallelize a real run.
- **First run needs internet; later runs don't.** Once weights are cached, analysis is fully offline
  and your photos never leave the machine.
