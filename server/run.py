"""Sidecar entrypoint — what PyInstaller freezes into `bin/cull-server` for the Tauri shell.

Also handy standalone: `python -m server.run --port 8756` then open http://127.0.0.1:8756.

Why the app is imported as an OBJECT, not the `"server.app:app"` string:
PyInstaller's static import analysis follows real `import` statements, not module paths passed
to uvicorn as strings. `uvicorn.run("server.app:app", ...)` would freeze a binary that crashes at
launch with `ModuleNotFoundError: server`, because `server.app` was never traced into the bundle.
Importing `app` here makes the dependency explicit so the freeze pulls in server/app.py (and,
through it, desktop_core.* and pipeline.*). It also drops the string target and `reload=` — a
reloader needs a string import and a watcher subprocess that does not exist in a frozen onefile.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


def _ensure_local_packages_importable() -> None:
    """Make `server`, `desktop_core`, `pipeline` importable when frozen.

    Under PyInstaller onefile the interpreter runs from the extracted `sys._MEIPASS` dir; the spec
    bundles the local packages there, but defensively put it on sys.path first. Running from source
    (`python -m server.run`) the repo root is already on sys.path, so this is a no-op.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))


def main() -> None:
    ap = argparse.ArgumentParser(prog="cull-server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8756)
    args = ap.parse_args()

    _ensure_local_packages_importable()

    # Import the FastAPI app OBJECT (not the "server.app:app" string) so PyInstaller traces it and
    # bundles server/app.py + desktop_core.* + pipeline.*. Imported here (after sys.path is fixed
    # up) rather than at module top so the frozen-path shim runs first.
    from server.app import app

    # Pass the app object; no reload (no string target, no watcher process in a frozen binary).
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
