# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — freezes the FastAPI sidecar into a single binary named `cull-server`.

Run from the REPO ROOT (not from desktop/):

    pyinstaller desktop/cull-server.spec

Output:  dist/cull-server   (onefile, no console window suppression — it logs to stderr, which the
Tauri shell forwards via CommandEvent::Stderr).

Tauri's `externalBin` requires the binary renamed with the Rust target-triple suffix. After this
runs, copy/rename it into place for the bundler, e.g. on Apple Silicon:

    mkdir -p desktop/src-tauri/bin
    cp dist/cull-server desktop/src-tauri/bin/cull-server-aarch64-apple-darwin

WHY EACH COLLECT EXISTS
-----------------------
- collect_all(torch / torchvision): ships the compiled extension modules AND the *.dylib runtime
  libs (libtorch_cpu.dylib, libomp.dylib, ...) and torch's data files (version.py, _C stubs). Torch
  loads these dylibs via dlopen at import; a plain submodule scan misses the binaries and the frozen
  binary dies with "Library not loaded: @rpath/libtorch_cpu.dylib".
- collect_all(open_clip): open_clip ships model-config JSON + bpe vocab data files (e.g.
  bpe_simple_vocab_16e6.txt.gz) loaded by pkg path at runtime; without datas, tokenizer creation
  raises FileNotFoundError. (PyPI dist is `open_clip_torch`; the IMPORT name is `open_clip`.)
- collect_all(cv2): opencv-python-headless is a single big extension plus its `cv2/data/` Haar
  cascades — pipeline/models.py reads `cv2.data.haarcascades + "haarcascade_*.xml"` at runtime, so
  those XML data files MUST be collected or Haar fallback face detection crashes.
- collect_all(rawpy): rawpy bundles the libraw dylib as a packaged binary; collect_all grabs it.
- collect_all(numpy / PIL): native extensions + (PIL) the plugin modules and any bundled data.
- collect_submodules(uvicorn): uvicorn picks its HTTP/WebSocket protocol, event loop, and lifespan
  implementations by STRING import at runtime (uvicorn.protocols.http.httptools_impl, ...websockets_impl,
  uvicorn.loop.uvloop, uvicorn.lifespan.on). Static analysis can't see these, so pull the whole tree
  plus the explicit hidden imports below.
- collect_submodules(server / desktop_core / pipeline): the local app packages. run.py imports
  `server.app`, which imports the rest; collecting the trees guards against any lazily-imported
  module (e.g. desktop_core.raw_preview does `import rawpy` inside functions).
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Repo root = the directory `pyinstaller` was invoked from (the docstring tells you to run it from
# the repo root). `__file__` is not defined inside a spec, so fall back to cwd, then to the spec's
# parent's parent if someone runs it from elsewhere.
REPO_ROOT = os.path.abspath(os.getcwd())
if not os.path.isdir(os.path.join(REPO_ROOT, "server")):
    # Best-effort: spec lives at <root>/desktop/cull-server.spec
    guess = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), ".."))
    if os.path.isdir(os.path.join(guess, "server")):
        REPO_ROOT = guess

ENTRY = os.path.join(REPO_ROOT, "server", "run.py")

# --- third-party libs that need their binaries + data files, not just .py submodules ---
datas = []
binaries = []
hiddenimports = []

for pkg in ("torch", "torchvision", "open_clip", "cv2", "rawpy", "numpy", "PIL"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# --- uvicorn[standard] dynamic impls (chosen by string import at runtime) ---
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    # http protocols
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.http.h11_impl",
    # websocket protocols
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    # event loops
    "uvicorn.loops.uvloop",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.auto",
    # lifespan
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # native deps these impls pull in
    "httptools",
    "websockets",
    "websockets.legacy",
    "wsproto",
    "uvloop",
    "h11",
    # ASGI / pydantic stack that FastAPI imports dynamically in spots
    "anyio",
    "anyio._backends._asyncio",
    "starlette",
    "pydantic",
]

# --- local application packages (the whole point: bundle the app) ---
for pkg in ("server", "desktop_core", "pipeline"):
    hiddenimports += collect_submodules(pkg)

# --- the built SPA ---------------------------------------------------------
# The Tauri webview loads an EXTERNAL url (http://127.0.0.1:8756) served by THIS frozen sidecar, not
# Tauri's bundled assets — so frontend/dist must live inside the binary or the app shows a blank page.
# Place it at "frontend/dist" so server/app.py's `<__file__>/../../frontend/dist` resolves under
# sys._MEIPASS (server/app.py is frozen-aware too). Build the SPA (`npm run build`) BEFORE freezing.
_spa = os.path.join(REPO_ROOT, "frontend", "dist")
if not os.path.isdir(_spa):
    raise SystemExit(
        "frontend/dist not found — run `npm --prefix frontend ci && npm --prefix frontend run build` "
        "before `pyinstaller desktop/cull-server.spec` (the frozen sidecar serves the SPA)."
    )
datas += [(_spa, "frontend/dist")]


block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[REPO_ROOT],            # so `import server` / `desktop_core` / `pipeline` resolve
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excludes trim the onefile so startup extraction is faster. None of these are imported by the
    # sidecar (no notebooks, no plotting, no test runner, no Tk GUI, no CUDA on this arm64 CPU build).
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
        "tcl",
        "tk",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="cull-server",           # MUST be exactly this; Tauri appends the target-triple on copy
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,                  # keep symbols; torch dylibs misbehave when stripped
    upx=False,                    # UPX corrupts torch/opencv dylibs — leave OFF
    upx_exclude=[],
    runtime_tmpdir=None,          # default per-run extraction under $TMPDIR (onefile)
    console=True,                 # logs to stderr; Tauri forwards it. No window: it's a sidecar.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",          # Apple Silicon only (matches the macos-14 CI runner)
    codesign_identity=None,       # UNSIGNED distribution by decision
    entitlements_file=None,
)
