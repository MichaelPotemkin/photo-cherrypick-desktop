# Desktop shell (Tauri) — M1

This wraps the local server + SPA into a downloadable macOS app. **It is a scaffold** — it was
not compiled in the prototype environment because the Rust toolchain isn't installed there. The
exact same backend runs standalone today (see the repo root README), so the desktop shell is the
packaging layer, not new functionality.

## Architecture

```
┌─ Photo Cherrypick.app ───────────────────────────────┐
│  Tauri (Rust) shell                                   │
│   • spawns sidecar  bin/cull-server  (PyInstaller)    │ ← the FastAPI server + bundled pipeline
│   • opens a webview onto http://127.0.0.1:8756        │ ← server serves the built SPA + API
│   • window.__TAURI__.dialog.open → native folder pick │
└───────────────────────────────────────────────────────┘
```

The Python sidecar is the `server.app` FastAPI process frozen with PyInstaller. Bundling torch +
open_clip makes the app large (~GB) — the Phase-2 plan is to swap CPU inference to ONNX-runtime to
shrink it (tracked in the PRD risks).

## Prerequisites (not present in the prototype env)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # Rust toolchain
cargo install tauri-cli --version '^2'
pip install pyinstaller
```

## Build

```bash
# 1. build the SPA
cd ../frontend && npm install && npm run build

# 2. freeze the Python server as the sidecar (named for Tauri's target triple)
cd ..
pyinstaller --onefile --name cull-server server/run.py
TRIPLE=$(rustc -Vv | sed -n 's/host: //p')
mkdir -p desktop/src-tauri/bin
cp dist/cull-server "desktop/src-tauri/bin/cull-server-$TRIPLE"

# 3. build the app
cd desktop/src-tauri && cargo tauri build      # -> .app + .dmg under target/release/bundle/
```

`server/run.py` is a tiny entrypoint: `uvicorn.run(server.app:app, host, port)` reading `--host/--port`.

## Code signing / notarization

A downloadable mac app must be Developer-ID signed + notarized or Gatekeeper blocks it. Configure
`bundle.macOS.signingIdentity` + an Apple notarization profile in `tauri.conf.json` / CI. (PRD risk.)

## Windows

Tauri builds Windows from the same Rust code; you'd produce a Windows-target PyInstaller sidecar
and `cargo tauri build` on Windows. Deferred to Phase 3.
