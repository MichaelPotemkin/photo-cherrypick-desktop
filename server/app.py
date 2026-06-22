"""Local FastAPI server for the desktop app.

Binds to 127.0.0.1 and is consumed by the Tauri webview (or a browser in dev). No auth token is
required — it's a single-user local process — but the `X-API-Token` header from the existing SPA
is accepted and ignored. Analysis runs in a single background worker thread (the pipeline model
singletons are not thread-safe); set `CULL_SYNC=1` to process inline (used by tests).
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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
        # the broad catch is deliberate (a background worker must report ANY failure, not crash the
        # thread), but log the full stack so an unexpected bug is diagnosable — not just reduced to a
        # one-line status string the user sees.
        traceback.print_exc(file=sys.stderr)
        store.set_status(sid, "error", f"{type(e).__name__}: {e}")


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    cache_dir = data_dir / "cache"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    store = CullStore(data_dir / "cull.db")
    executor = ThreadPoolExecutor(max_workers=1)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        # graceful teardown: stop the analysis worker pool on shutdown so we don't leak a running
        # thread (cancel anything still queued; don't block the exit on an in-flight analysis).
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Photo Cherrypick (desktop)", lifespan=lifespan)
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
    def export(sid: str, format: str = "zip", check: bool = False):
        # format="zip": all favorites + maybes as the untouched originals (+ XMP sidecars).
        # format="gallery": the favorites only, in planned Feed order, slot-numbered for posting.
        if not store.get_session(sid):
            raise HTTPException(404, "unknown session")
        if format not in ("zip", "gallery"):
            raise HTTPException(400, f"bad format: {format}")
        if check:
            # cheap pre-flight (no zip built): how many selected originals are actually on disk, so
            # the UI can warn before downloading instead of handing back an empty/short archive.
            return export_mod.export_preflight(store, sid, feed=(format == "gallery"))

        fd, tmp_name = tempfile.mkstemp(suffix=".zip", prefix="cull_")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            if format == "gallery":
                export_mod.export_feed_to_zip(store, sid, tmp)
            else:
                export_mod.export_to_zip(store, sid, tmp)
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, str(e))
        except Exception:
            tmp.unlink(missing_ok=True)  # don't leak a partial temp zip on any failure
            raise
        sess = store.get_session(sid)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (sess["title"] or "picks"))
        kind = "gallery" if format == "gallery" else "picks"
        # delete the temp zip after it's been streamed to the client
        return FileResponse(
            tmp, media_type="application/zip", filename=f"{safe}_{kind}.zip",
            background=BackgroundTask(lambda p=tmp: p.unlink(missing_ok=True)),
        )

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
        # Thumb/preview are generated once at ingest and addressed by (photo id, size) — effectively
        # immutable — so let the webview cache them instead of re-fetching every grid scroll / relaunch.
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    # --- SPA static (served at / when built) ---
    # Serve hashed build assets from /assets, and fall everything else back to index.html so a hard
    # refresh / deep link to a client-side route (e.g. /session/<id>) doesn't 404. Registered after
    # the /api routes, so those still win; /api/* 404s stay JSON.
    # When frozen (PyInstaller onefile, in the Tauri app), the SPA is bundled under sys._MEIPASS;
    # from source it's <repo>/frontend/dist. Both land at <base>/frontend/dist.
    if getattr(sys, "frozen", False):
        spa_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    else:
        spa_base = Path(__file__).resolve().parent.parent
    spa = spa_base / "frontend" / "dist"
    if spa.is_dir():
        spa_root = spa.resolve()
        index_html = spa / "index.html"
        if (spa / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=str(spa / "assets")), name="assets")

        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            candidate = (spa / full_path).resolve()
            # serve a real top-level file (favicon, etc.); guard against path traversal.
            # /assets/* are content-hashed (immutable) so they stay cacheable.
            if full_path and candidate.is_file() and spa_root in candidate.parents:
                return FileResponse(candidate)
            # The SPA entry MUST NOT be cached: the Tauri webview persists its cache across app
            # versions, so after an auto-update a cached index.html would keep pointing at the old
            # hashed bundle and the new UI would never appear. no-store forces a fresh entry every
            # launch (the hashed assets it references are then fetched normally).
            return FileResponse(index_html, headers={"Cache-Control": "no-store"})
    else:
        # No built SPA at <base>/frontend/dist. In a frozen build this means a broken bundle
        # (the spec copies the SPA there at freeze time); from source it just means `npm run build`
        # hasn't run. Either way, leave the catch-all registered so `/` is HANDLED — without it the
        # webview would load a blank page / bare 404 with no clue why. Warn loudly at startup and
        # serve a readable HTML page instead.
        fix = (
            "reinstall the app — this build is missing its bundled UI"
            if getattr(sys, "frozen", False)
            else "run `npm run build` in frontend/ (or `npm run dev` for the live dev server)"
        )
        print(
            f"WARNING: SPA not found at {spa} — the UI will not load. To fix: {fix}.",
            file=sys.stderr,
        )
        _missing_spa_html = (
            "<!doctype html><meta charset=utf-8>"
            "<title>UI not found</title>"
            "<body style=\"font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:4rem auto;padding:0 1rem\">"
            "<h1>UI not found</h1>"
            f"<p>The app's web UI wasn't found at <code>{spa}</code>, so the API is running but "
            "there's nothing to show.</p>"
            f"<p><b>To fix:</b> {fix}.</p>"
            "</body>"
        )

        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def spa_missing(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            return HTMLResponse(_missing_spa_html, status_code=503)

    return app


app = create_app()
