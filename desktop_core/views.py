"""Read-model builders: turn stored rows into the JSON shapes the SPA expects.

Kept separate from the web layer so they're unit-testable without FastAPI. Mirrors the hosted
`app/routers/groups.py` photo/group/session shapes, except image URLs point at the local
`/api/img/{id}/{size}` endpoint (served from disk) instead of a CDN.
"""
from __future__ import annotations

from datetime import datetime

from pipeline.scene_group import build_scene_groups

from .constants import CLOSE_GAP
from .feed import plan_feed, shot_scale
from .store import CullStore


def when_str(ctime: float | None) -> str:
    if not ctime:
        return ""
    try:
        return datetime.fromtimestamp(ctime).strftime("%b %d, %H:%M")
    except (ValueError, OSError):
        return ""


def _img(pid: str, size: str) -> str:
    return f"/api/img/{pid}/{size}"


def session_summary(store: CullStore, sess: dict) -> dict:
    return {
        "id": sess["id"],
        "title": sess["title"],
        "status": sess["status"],
        "n_total": sess["n_total"],
        "counts": store.counts(sess["id"], sess["n_total"]),
        # undecided best-of-burst picks "Accept picks" will favorite — authoritative, view-independent
        "n_suggestions": store.count_pending_suggestions(sess["id"]),
    }


def session_detail(store: CullStore, sess: dict) -> dict:
    return {
        "id": sess["id"],
        "title": sess["title"],
        "source_url": sess["source_path"],   # keep the SPA's field name; value is a local path
        "status": sess["status"],
        "n_total": sess["n_total"],
        "n_done": sess["n_done"],
        "error": sess["error"],
        "counts": store.counts(sess["id"], sess["n_total"]),
    }


def session_list_item(store: CullStore, sess: dict) -> dict:
    return {
        "id": sess["id"],
        "title": sess["title"],
        "source_url": sess["source_path"],
        "status": sess["status"],
        "n_total": sess["n_total"],
        "n_done": sess["n_done"],
        "created_at": datetime.fromtimestamp(sess["created_at"]).isoformat() if sess["created_at"] else None,
        "counts": store.counts(sess["id"], sess["n_total"]),
    }


def _photo_obj(pid: str, photo: dict, a: dict, state: str, suggested: bool) -> dict:
    """Shared per-photo JSON shape used by both grouping modes."""
    return {
        "id": pid,
        "filename": photo["filename"],
        "when": when_str(photo["ctime"]),
        "suggested": suggested,
        "overall": round(a["overall"] or 0.0, 3),
        "reasons": a["reasons"],
        "axes": a["axes"],
        "cats": a["cats"],
        "is_bw": bool((a["meta"] or {}).get("is_bw")),
        "state": state,
        "preview_url": _img(pid, "preview"),
        "original_url": _img(pid, "original"),
    }


def groups_response(store: CullStore, sid: str, mode: str = "burst") -> dict | None:
    """Build the grouped read-model.

    mode="burst" (default): the persisted first-pass burst groups (near-duplicate frames).
    mode="scene": on-demand greedy clustering of the *keepers* (trashed photos excluded) into
                  scenes/outfits for the second pass — computed fresh from stored embeddings, not
                  persisted, so it always reflects the current cull state with no re-analysis.
    """
    sess = store.get_session(sid)
    if not sess:
        return None
    photos = {p["id"]: p for p in store.list_photos(sid)}
    analyses = store.get_analyses(sid)
    states = store.current_states(sid)

    if mode == "scene":
        groups = _scene_groups(store, sid, photos, analyses, states)
    else:
        groups = _burst_groups(store, sid, photos, analyses, states)

    return {"session": session_summary(store, sess), "groups": groups}


def _burst_groups(store: CullStore, sid: str, photos: dict, analyses: dict, states: dict) -> list[dict]:
    meta_groups = store.get_groups(sid)
    by_group: dict[int, list[dict]] = {}
    for pid, a in analyses.items():
        photo = photos.get(pid)
        if photo is None:
            continue
        obj = _photo_obj(pid, photo, a, states.get(pid, "none"), bool(a["suggested"]))
        obj["_order"] = a["in_group_order"]
        by_group.setdefault(a["group_idx"], []).append(obj)

    groups = []
    for g in meta_groups:
        members = sorted(by_group.get(g["idx"], []), key=lambda o: o["_order"])
        for o in members:
            o.pop("_order", None)
        groups.append({
            "idx": g["idx"],
            "label": g["label"],
            "when": when_str(g["when_ts"]),
            "avg_score": round(g["avg_score"] or 0.0, 3),
            "close_call": bool(g.get("close_call")),
            "photos": members,
        })
    return groups


def feed_response(store: CullStore, sid: str) -> dict | None:
    """Ordered feed of the FAVORITES, arranged for a balanced gallery/IG grid (see feed.plan_feed).
    Each photo carries a `scale` (close/medium/wide) and 1-based `slot`."""
    sess = store.get_session(sid)
    if not sess:
        return None
    photos = {p["id"]: p for p in store.list_photos(sid)}
    analyses = store.get_analyses(sid)
    states = store.current_states(sid)
    embs = store.get_embeddings(sid)

    records = []
    for pid, a in analyses.items():
        if states.get(pid, "none") != "favorite":   # the feed is the committed keepers
            continue
        photo = photos.get(pid)
        if photo is None:
            continue
        meta = a["meta"] or {}
        records.append({
            "id": pid, "emb": embs.get(pid),
            # pass n_faces through UNMODIFIED (None for pre-n_faces analyses) so shot_scale can tell
            # "detector found nobody" (0) from "field didn't exist yet" (None) and fall back to face_frac.
            "face_frac": meta.get("face_frac"), "n_faces": meta.get("n_faces"),
            "overall": a["overall"] or 0.0,
        })

    items = []
    for pos, rec in enumerate(plan_feed(records)):
        pid = rec["id"]
        obj = _photo_obj(pid, photos[pid], analyses[pid], states.get(pid, "none"), False)
        obj["scale"] = shot_scale(rec)
        obj["slot"] = pos + 1
        items.append(obj)
    return {"session": session_summary(store, sess), "photos": items}


def _scene_groups(store: CullStore, sid: str, photos: dict, analyses: dict, states: dict) -> list[dict]:
    embs = store.get_embeddings(sid)
    records = []
    for pid, a in analyses.items():
        photo = photos.get(pid)
        if photo is None or pid not in embs:
            continue
        if states.get(pid, "none") == "delete":  # second pass: trashed photos are out
            continue
        records.append({
            "id": pid,
            "emb": embs[pid],
            "ctime": photo["ctime"],
            "overall": a["overall"] or 0.0,
        })

    clusters = build_scene_groups(records)
    groups = []
    for gi, cluster in enumerate(clusters):
        members = []
        for oi, rec in enumerate(cluster):
            pid = rec["id"]
            suggested = oi == 0  # best frame of the scene (a single-frame scene's only frame is it)
            members.append(_photo_obj(pid, photos[pid], analyses[pid], states.get(pid, "none"), suggested))
        n = len(cluster)
        ctimes = [photos[rec["id"]]["ctime"] for rec in cluster if photos[rec["id"]]["ctime"]]
        avg = sum(rec["overall"] for rec in cluster) / n if n else 0.0
        top2 = sorted((rec["overall"] for rec in cluster), reverse=True)[:2]
        close = len(top2) == 2 and (top2[0] - top2[1]) < CLOSE_GAP
        groups.append({
            "idx": gi,
            # "unique look" (not "single shot") so a 1-photo scene reads differently from a 1-photo
            # burst — here it means "the only keeper of this look", not "an un-bursted frame".
            "label": f"{n} in scene" if n > 1 else "unique look",
            "when": when_str(min(ctimes)) if ctimes else "",
            "avg_score": round(avg, 3),
            "close_call": close,
            "photos": members,
        })
    return groups
