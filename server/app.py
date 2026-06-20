"""Local FastAPI server for the desktop app.

Binds to 127.0.0.1 and is consumed by the Tauri webview (or a browser in dev). No auth token is
required — it's a single-user local process — but the `X-API-Token` header from the existing SPA
is accepted and ignored. Analysis runs in a single background worker thread (the pipeline model
singletons are not thread-safe); set `CULL_SYNC=1` to process inline (used by tests).
"""
from __future__ import annotations

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from desktop_core import export as export_mod
from desktop_core import pipeline_runner, views
from desktop_core.ingest import scan_folder
from desktop_core.raw_preview import JPEG_EXTS, OTHER_IMAGE_EXTS
from desktop_core.store import ACTIONS, CullStore

DATA_DIR = Path(os.environ.get("CULL_DATA_DIR", Path.home() / ".photo-cherrypick-desktop"))
CACHE_DIR = DATA_DIR / "cache"
RUN_SYNC = os.environ.get("CULL_SYNC") == "1"
_VIEWABLE = JPEG_EXTS | OTHER_IMAGE_EXTS | {".png"}


class CreateSession(BaseModel):
    path: str = Field(min_length=1)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Decision(BaseModel):
    action: str


def _process(store: CullStore, sid: str, folder: str) -> None:
    try:
        pipeline_runner.warmup()
        items = scan_folder(folder)
        pipeline_runner.run_session(store, sid, items, CACHE_DIR / sid)
    except Exception as e:  # surface to the UI rather than dying silently
        store.set_status(sid, "error", f"{type(e).__name__}: {e}")


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    cache_dir = data_dir / "cache"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    store = CullStore(data_dir / "cull.db")
    executor = ThreadPoolExecutor(max_workers=1)
    app = FastAPI(title="Photo Cherrypick (desktop)")
    # The packaged app serves the SPA same-origin (StaticFiles below), so CORS is only needed for
    # the dev SPA (vite) and the Tauri webview. A wildcard would let any website the user visits
    # drive/read this unauthenticated local API — scope it to known local origins instead.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", "http://127.0.0.1:5173",  # vite dev
            "tauri://localhost", "http://tauri.localhost",       # packaged webview
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = store
    app.state.cache_dir = cache_dir

    def submit(sid: str, folder: str) -> None:
        if RUN_SYNC:
            _process(store, sid, folder)
        else:
            executor.submit(_process, store, sid, folder)

    # --- sessions ---
    @app.post("/api/sessions")
    def create_session(body: CreateSession):
        folder = Path(body.path).expanduser()
        if not folder.is_dir():
            raise HTTPException(400, f"not a folder: {body.path}")
        sid = store.create_session(str(folder))
        submit(sid, str(folder))
        sess = store.get_session(sid)
        return {"id": sid, "title": sess["title"], "n_total": 0, "status": sess["status"]}

    @app.get("/api/sessions")
    def list_sessions():
        return [views.session_list_item(store, s) for s in store.list_sessions()]

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        sess = store.get_session(sid)
        if not sess:
            raise HTTPException(404, "unknown session")
        return views.session_detail(store, sess)

    @app.patch("/api/sessions/{sid}")
    def rename_session(sid: str, body: Rename):
        if not store.rename(sid, body.title):
            raise HTTPException(404, "unknown session")
        return {"id": sid, "title": body.title.strip()}

    @app.delete("/api/sessions/{sid}")
    def delete_session(sid: str):
        if not store.delete_session(sid):
            raise HTTPException(404, "unknown session")
        for f in cache_dir.glob(f"{sid}/*"):  # best-effort cache cleanup
            try:
                f.unlink()
            except OSError:
                pass
        return {"deleted": sid}

    @app.get("/api/sessions/{sid}/groups")
    def get_groups(sid: str, mode: str = "burst"):
        if mode not in ("burst", "scene"):
            raise HTTPException(400, f"bad mode: {mode}")
        data = views.groups_response(store, sid, mode)
        if data is None:
            raise HTTPException(404, "unknown session")
        return data

    @app.get("/api/sessions/{sid}/feed")
    def get_feed(sid: str):
        data = views.feed_response(store, sid)
        if data is None:
            raise HTTPException(404, "unknown session")
        return data

    @app.post("/api/sessions/{sid}/accept-suggestions")
    def accept_suggestions(sid: str):
        if not store.get_session(sid):
            raise HTTPException(404, "unknown session")
        accepted = store.accept_suggestions(sid)
        return {"accepted": accepted, "counts": store.counts(sid)}

    # --- decisions ---
    @app.post("/api/photos/{pid}/decision")
    def decide(pid: str, body: Decision):
        if body.action not in ACTIONS:
            raise HTTPException(400, f"bad action: {body.action}")
        photo = store.get_photo(pid)
        if not photo:
            raise HTTPException(404, "unknown photo")
        state = store.add_decision(photo["session_id"], pid, body.action)
        return {"state": state}

    # --- export ---
    @app.get("/api/sessions/{sid}/export")
    def export(sid: str, format: str = "zip"):
        if not store.get_session(sid):
            raise HTTPException(404, "unknown session")
        if format == "zip":
            fd, tmp_name = tempfile.mkstemp(suffix=".zip", prefix="cull_")
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                export_mod.export_to_zip(store, sid, tmp)
            except ValueError as e:
                tmp.unlink(missing_ok=True)
                raise HTTPException(400, str(e))
            except Exception:
                tmp.unlink(missing_ok=True)  # don't leak a partial temp zip on any failure
                raise
            sess = store.get_session(sid)
            safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (sess["title"] or "picks"))
            # delete the temp zip after it's been streamed to the client
            return FileResponse(
                tmp, media_type="application/zip", filename=f"{safe}_picks.zip",
                background=BackgroundTask(lambda p=tmp: p.unlink(missing_ok=True)),
            )
        raise HTTPException(400, f"bad format: {format}")

    # --- local image serving (replaces the CDN 302 redirect) ---
    @app.get("/api/img/{pid}/{size}")
    def image(pid: str, size: str):
        photo = store.get_photo(pid)
        if not photo:
            raise HTTPException(404, "unknown photo")
        if size == "thumb":
            path = photo["thumb_path"]
        elif size == "preview":
            path = photo["preview_path"]
        elif size == "original":
            # full-res original only if browser-viewable; RAW falls back to the cached preview
            orig = photo["original_path"]
            path = orig if (Path(orig).suffix.lower() in _VIEWABLE and Path(orig).exists()) else photo["preview_path"]
        else:
            raise HTTPException(404, "unknown size")
        if not path or not Path(path).exists():
            raise HTTPException(404, "image not available")
        return FileResponse(path)

    # --- SPA static (served at / when built) ---
    # Serve hashed build assets from /assets, and fall everything else back to index.html so a hard
    # refresh / deep link to a client-side route (e.g. /session/<id>) doesn't 404. Registered after
    # the /api routes, so those still win; /api/* 404s stay JSON.
    spa = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if spa.is_dir():
        spa_root = spa.resolve()
        index_html = spa / "index.html"
        if (spa / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=str(spa / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            candidate = (spa / full_path).resolve()
            # serve a real top-level file (favicon, etc.); guard against path traversal
            if full_path and candidate.is_file() and spa_root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index_html)

    return app


app = create_app()
