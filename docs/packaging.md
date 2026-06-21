# Packaging — freezing the sidecar with PyInstaller

How the Python FastAPI **sidecar** is frozen into a single binary, bundled into the Tauri app, and
shipped by the release pipeline. The authoritative source is the heavily-commented spec at
[`desktop/cull-server.spec`](../desktop/cull-server.spec) and the freeze step in
[`.github/workflows/release-macos.yml`](../.github/workflows/release-macos.yml); this doc explains
*why* it's shaped the way it is, so you don't break the freeze by accident (or get stuck debugging
one).

## What the sidecar is, and why it's frozen

The app's analysis core is Python: the FastAPI server (`server/`), the local-first I/O layer
(`desktop_core/`), and the torch + open_clip + OpenCV scoring/grouping pipeline (`pipeline/`). The
Tauri shell (`desktop/src-tauri/`) is a thin native window that, on launch, spawns this Python
process as a **sidecar** and points its WKWebView at `http://127.0.0.1:8756` — the URL the sidecar
serves. The webview loads that **external URL**, not Tauri's own bundled assets.

End users don't have Python (let alone the pinned torch/open_clip/rawpy versions) installed. So the
whole sidecar — interpreter, every dependency, the native dylibs, and the built SPA — is **frozen**
into one self-contained executable with [PyInstaller](https://pyinstaller.org/). The frozen binary
is what the Tauri bundle ships and runs; there is no separate Python install on the user's machine,
and the app works fully offline (it only reaches the network once, to download model weights on
first run).

## How the spec works

### onefile

The spec builds a **onefile** binary: `EXE(...)` with `runtime_tmpdir=None`. Everything (the
interpreter, the `.pyz` of pure-Python modules, the native binaries, and the data files) is packed
into a single executable. At launch the bootloader extracts that payload to a per-run temp dir under
`$TMPDIR` and runs from there; that extracted root is `sys._MEIPASS`.

`console=True` does **not** mean a window — it's a headless sidecar. It means the process logs to
stderr, which the Tauri shell forwards (via `CommandEvent::Stderr`). `strip=False` and `upx=False`
are deliberate: stripping symbols or UPX-compressing corrupts the torch/OpenCV dylibs and the binary
dies at import. `target_arch="arm64"` matches the Apple-Silicon-only distribution and the `macos-14`
CI runner.

> **Per-launch extraction cost:** onefile re-extracts the ~200 MB ML runtime to a temp dir on
> **every** launch (measured ~34s cold), which is the root cause of the slow/blank first window.
> Switching to PyInstaller **onedir** (ship the runtime already extracted) removes that unpack — it's
> tracked in **[issue #93](https://github.com/MichaelPotemkin/photo-cherrypick-desktop/issues/93)**.
> Don't implement it here; just know that's why onefile is slow to start.

### Why the entrypoint imports the app object (not a string)

The frozen entrypoint is `server/run.py`. It calls `uvicorn.run(app, ...)` with the **imported app
object**, *not* `uvicorn.run("server.app:app", ...)`. This is load-bearing for the freeze:
PyInstaller's static analysis follows real `import` statements, not module paths passed to uvicorn
as strings. A string target would freeze a binary that crashes at launch with
`ModuleNotFoundError: server`, because `server.app` was never traced into the bundle. Importing the
object makes the dependency explicit (and drops `reload=`, which needs a string target and a watcher
subprocess that don't exist in a frozen onefile). If you change that line back to a string, the
freeze will look fine and the app will die on startup.

### Why `collect_all` is needed (torch / torchvision / open_clip / cv2 / rawpy / numpy / PIL)

A plain submodule scan only finds importable `.py` modules. These packages ship **native binaries
and data files** that are loaded at runtime by path/dlopen, which static analysis can't see — so the
spec runs `collect_all(pkg)` for each to pull in their `datas`, `binaries`, and hidden imports:

- **torch / torchvision** — ship compiled extension modules **and** the `*.dylib` runtime libs
  (`libtorch_cpu.dylib`, `libomp.dylib`, …) plus data files. Torch `dlopen`s those dylibs at import;
  a plain scan misses them and the binary dies with
  `Library not loaded: @rpath/libtorch_cpu.dylib`.
- **open_clip** — ships model-config JSON + bpe vocab data files (e.g.
  `bpe_simple_vocab_16e6.txt.gz`) loaded by package path at runtime; without those datas, tokenizer
  creation raises `FileNotFoundError`. (The PyPI dist is `open_clip_torch`; the **import** name is
  `open_clip`.)
- **cv2** — opencv-python-headless is one big extension plus its `cv2/data/` Haar cascades;
  `pipeline/models.py` reads `cv2.data.haarcascades + "haarcascade_*.xml"` at runtime, so those XML
  data files must be collected or the Haar fallback face detection crashes.
- **rawpy** — bundles the `libraw` dylib as a packaged binary; `collect_all` grabs it.
- **numpy / PIL** — native extensions, plus (PIL) the plugin modules and any bundled data.

### uvicorn's dynamic submodules

uvicorn[standard] picks its HTTP/WebSocket protocol, event loop, and lifespan implementations by
**string import at runtime** (e.g. `uvicorn.protocols.http.httptools_impl`,
`uvicorn.protocols.websockets.websockets_impl`, `uvicorn.loops.uvloop`, `uvicorn.lifespan.on`).
Static analysis can't see those, so the spec pulls the whole tree with
`collect_submodules("uvicorn")` **and** lists explicit hidden imports for the protocol/loop/lifespan
impls plus the native deps they reach for (`httptools`, `websockets`, `wsproto`, `uvloop`, `h11`,
`anyio`, `starlette`, `pydantic`).

### Local app packages

`run.py` imports `server.app`, which imports the rest of the app. The spec additionally runs
`collect_submodules` over `server`, `desktop_core`, and `pipeline` to guard against any
lazily-imported module (e.g. `desktop_core.raw_preview` does `import rawpy` inside a function, so a
top-level trace alone might miss it).

### The embedded SPA (`frontend/dist`)

Because the webview loads the sidecar's URL (not Tauri's bundled assets), the **built SPA must live
inside the binary** — otherwise the app shows a blank page. The spec adds the built SPA as a data
dir mapped to `frontend/dist`:

```python
datas += [(_spa, "frontend/dist")]
```

It's placed there on purpose: when frozen, `server/app.py` resolves the SPA under
`sys._MEIPASS / "frontend" / "dist"` (and from source it's `<repo>/frontend/dist` — both land at the
same relative path), then mounts it with `StaticFiles`. The spec **hard-fails** if `frontend/dist`
is missing, so you must build the SPA **before** freezing.

### The excludes

The spec excludes `tkinter`, `matplotlib`, `IPython`, `notebook`, `pytest`, `tcl`, and `tk`. None of
them are imported by the sidecar (no notebooks, no plotting, no test runner, no Tk GUI, no CUDA on
this arm64 CPU/MPS build); excluding them trims the onefile payload so the per-launch extraction is
faster.

## The target-triple rename Tauri requires

PyInstaller emits `dist/cull-server`. Tauri's `externalBin` mechanism requires the sidecar binary to
be renamed with the Rust **target-triple** suffix and placed where the bundler looks for it. On
Apple Silicon:

```bash
mkdir -p desktop/src-tauri/bin
cp dist/cull-server desktop/src-tauri/bin/cull-server-aarch64-apple-darwin
```

The name `cull-server` in the spec's `EXE(name=...)` must stay exactly that — Tauri appends the
triple on copy.

## How the release pipeline ties it together

`.github/workflows/release-macos.yml` runs on a tag matching `v*`, on the `macos-14` (arm64) runner.
The order matters — **SPA first, then freeze, then bundle:**

1. **Check prerequisites** — assert the tag matches `tauri.conf.json`'s version and that the updater
   signing secret (`TAURI_SIGNING_PRIVATE_KEY`) is set.
2. **Build the SPA first** — `npm ci && npm run build` in `frontend/`, producing `frontend/dist`,
   because the frozen sidecar bundles and serves it.
3. **Freeze the sidecar** — install `requirements.txt` + `pyinstaller==6.11.1`, then
   `pyinstaller --noconfirm desktop/cull-server.spec`. (On macOS arm64 the default PyPI
   torch/torchvision wheels are the CPU/MPS arm64 builds, so a plain install matches the pins.) Then
   rename to the target triple, `chmod +x`, and **ad-hoc sign** it (`codesign --force --sign -`) so
   the nested Mach-O has a valid signature — arm64 refuses to launch unsigned Mach-O.
4. **Build + release with Tauri** — `tauri-apps/tauri-action` builds the `.app`/`.dmg` for
   `aarch64-apple-darwin`, ad-hoc signs the bundle (`APPLE_SIGNING_IDENTITY: '-'`), and creates the
   GitHub Release. With the updater signing secrets present it also signs the `.app.tar.gz` updater
   artifact, emits its `.sig`, and writes `latest.json` for the in-app auto-updater.

Distribution is **unsigned** (no Apple Developer ID / no notarization); the ad-hoc signatures are
only what arm64 needs to launch the binary at all. End users approve the app once via Gatekeeper. See
[`RELEASING.md`](../RELEASING.md) for the full release runbook and one-time updater-key setup.

## Building / freezing locally

Run from the **repo root** (the spec resolves `REPO_ROOT` from the current working directory).

```bash
# 1. Build the SPA first — the frozen sidecar bundles + serves it.
npm --prefix frontend ci && npm --prefix frontend run build

# 2. Freeze the sidecar.
pyinstaller desktop/cull-server.spec
# -> dist/cull-server   (onefile; logs to stderr)

# 3. Rename with the Rust target triple for Tauri's externalBin (Apple Silicon).
mkdir -p desktop/src-tauri/bin
cp dist/cull-server desktop/src-tauri/bin/cull-server-aarch64-apple-darwin
```

You can also run the sidecar straight from source without freezing, to sanity-check the server side:

```bash
python -m server.run --port 8756   # then open http://127.0.0.1:8756
```

## Debugging a broken freeze

- **The binary logs to stderr.** Run `dist/cull-server` (or `python -m server.run`) directly in a
  terminal and read the traceback — that's the fastest signal.
- **`ModuleNotFoundError` at launch** usually means a module was string-imported (uvicorn dynamic
  impl, or `server.app` passed as a string) and never traced. Add it to `hiddenimports` (or restore
  the object import in `run.py`).
- **`Library not loaded: @rpath/...` / `FileNotFoundError` for a data file** means a package's
  binaries/datas weren't collected — make sure it's in the `collect_all` loop, and keep `strip` and
  `upx` **off**.
- **Blank window** usually means `frontend/dist` wasn't built before freezing (the spec hard-fails
  on a missing SPA) or wasn't served from `sys._MEIPASS/frontend/dist`.
- Adding a new heavy dependency (e.g. ONNX in a later phase) almost always means adding a
  `collect_all` for it and testing the frozen binary end-to-end, not just the source run.
