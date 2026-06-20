"""Sidecar entrypoint — what PyInstaller freezes into `bin/cull-server` for the Tauri shell.

Also handy standalone: `python -m server.run --port 8756` then open http://127.0.0.1:8756.
"""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(prog="cull-server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8756)
    args = ap.parse_args()
    uvicorn.run("server.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
