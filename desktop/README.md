# Desktop shell (Tauri)

This wraps the local server + SPA into a downloadable macOS app. Releases are built and published by
GitHub Actions on a `v*` tag (`.github/workflows/release-macos.yml`) — see **[../RELEASING.md](../RELEASING.md)**
for the runbook and **[../README.md](../README.md#download-macos)** for install/auto-update notes.
The Rust toolchain isn't installed in every dev environment, so you may only be able to build locally
on a machine with `rustup` + the Tauri CLI; the same backend always runs standalone too (repo root README).

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

`server/run.py` is a tiny entrypoint that imports the FastAPI **app object** (`from server.app import app`)
so PyInstaller traces `server`/`desktop_core`/`pipeline` into the freeze; it reads `--host/--port`.
Note: the Tauri webview loads the **external** server URL, so `desktop/cull-server.spec` bundles
`frontend/dist` into the binary — build the SPA before freezing.

## Code signing / notarization

v1.0 ships **unsigned** (no Apple Developer ID, no notarization) — by decision, to keep it free. CI
ad-hoc signs the bundle (`APPLE_SIGNING_IDENTITY: '-'`) so Apple Silicon will launch it; users clear
Gatekeeper once (right-click → Open / `xattr`, documented in the root README). The free **minisign**
key used by the updater is unrelated to Apple signing (see RELEASING.md).

## Auto-update

`tauri-plugin-updater` is wired: on launch the app checks the GitHub Release `latest.json` and installs
a newer signed build in place. Free; hosted on GitHub Releases. See RELEASING.md for the key setup.

## Windows

Tauri builds Windows from the same Rust code; you'd produce a Windows-target PyInstaller sidecar
and `cargo tauri build` on Windows. Deferred to Phase 3.
