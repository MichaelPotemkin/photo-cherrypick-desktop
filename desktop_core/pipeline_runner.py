"""Session orchestration — the local equivalent of the hosted app's worker.

Mirrors `app/worker.py`'s sequence exactly, adapted to local files + SQLite:
  load (preview-first) -> analyze -> compute per-session refs -> build burst groups ->
  per-group suggestion sort (with blink penalty) -> persist analyses + group metadata.

Analysis is run **sequentially** because the CV/torch model singletons in `pipeline/` are not
thread-safe (see the reuse contract). Call `warmup()` once before processing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from pipeline import models
from pipeline.analyze import analyze
from pipeline.embed import camera_id, capture_time
from pipeline.group import build_groups
from pipeline.score import axis_scores, compute_refs
from pipeline.select import rank_burst

from .ingest import FileItem
from .raw_preview import load_rgb, make_thumbnail
from .store import CullStore

# analyze() keys that are stored as columns / not part of the raw "meta" blob (mirrors worker._NON_META_KEYS)
_NON_META = {"emb", "id", "name", "camera", "path", "load_path"}

PREVIEW_MAX = 1600
THUMB_MAX = 480
# in a multi-shot burst, if the top-2 picks are within this overall margin the choice is a
# near-tie — flag it so the UI can tell the photographer "too close to call, you decide".
# 0.05 calibrated on the audit shoot: picks below it are ~coin-flips vs the reference panel
# (it more than halves confidently-wrong unflagged picks). See docs/SCORING-ITERATION-LOG.md.
_CLOSE_GAP = 0.05


def warmup() -> None:
    """Force-load all pipeline models once (single-threaded) before processing."""
    models.warmup()


def _cache_previews(img, pid: str, cache_dir: Path) -> tuple[str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    preview_path = cache_dir / f"{pid}_preview.jpg"
    thumb_path = cache_dir / f"{pid}_thumb.jpg"
    make_thumbnail(img, PREVIEW_MAX).save(preview_path, "JPEG", quality=88)
    make_thumbnail(img, THUMB_MAX).save(thumb_path, "JPEG", quality=82)
    return str(preview_path), str(thumb_path)


def run_session(
    store: CullStore,
    sid: str,
    items: list[FileItem],
    cache_dir: str | Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Process all items for a session end-to-end. Returns a small summary dict."""
    cache_dir = Path(cache_dir)
    store.set_status(sid, "processing")
    store.set_total(sid, len(items))

    records: list[dict] = []
    unsupported: list[str] = []

    for i, item in enumerate(items):
        pid = store.add_photo(sid, item.filename, item.original_path, item.is_raw)
        img = load_rgb(Path(item.load_path))
        if img is None:
            unsupported.append(item.filename)
            if on_progress:
                on_progress(i + 1, len(items))
            store.set_progress(sid, i + 1)
            continue

        preview_path, thumb_path = _cache_previews(img, pid, cache_dir)
        store.set_photo_cache(pid, preview_path, thumb_path)

        exif = img.getexif()
        ctime = capture_time(exif)
        camera = camera_id(exif, item.filename)
        store.set_photo_meta(pid, camera, ctime)

        rec = analyze(img, ctime)
        rec["id"] = pid
        rec["name"] = item.filename
        rec["camera"] = camera
        records.append(rec)

        if on_progress:
            on_progress(i + 1, len(items))
        store.set_progress(sid, i + 1)

    if not records:
        store.set_status(sid, "ready")
        return {"analyzed": 0, "unsupported": unsupported, "groups": 0}

    # per-session refs, then burst grouping (camera -> time -> similarity -> pose)
    refs = compute_refs(records)
    groups = build_groups(records, refs)

    for gi, g in enumerate(groups):
        ordered = [g[i] for i in rank_burst(g, refs)]   # single source of truth (pipeline/select)
        overalls: list[float] = []
        for oi, r in enumerate(ordered):
            axes, cats, overall, reasons = axis_scores(r, refs)
            overalls.append(overall)
            meta = {k: v for k, v in r.items() if k not in _NON_META}
            store.save_analysis(
                r["id"], emb=r.get("emb"), meta=meta, axes=axes, cats=cats,
                overall=overall, reasons=reasons, group_idx=gi, in_group_order=oi,
                suggested=(len(g) > 1 and oi == 0),
            )
        label = f"{len(g)} in burst — pick one" if len(g) > 1 else "single shot"
        when_ts = g[0].get("ctime")
        avg = sum(overalls) / len(overalls) if overalls else 0.0
        # close call = multi-shot burst whose best two frames are within _CLOSE_GAP
        top2 = sorted(overalls, reverse=True)[:2]
        close = len(top2) == 2 and (top2[0] - top2[1]) < _CLOSE_GAP
        store.save_group(sid, gi, label, when_ts, avg, close_call=close)

    store.set_status(sid, "ready")
    return {"analyzed": len(records), "unsupported": unsupported, "groups": len(groups)}
