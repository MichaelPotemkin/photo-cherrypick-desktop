"""Burst grouping. Lifted from cull_server.py: partition by camera body, walk each body's
timeline, break a burst when the time gap, visual similarity, OR subject pose change crosses
a threshold; order groups best-first by average overall score.

Records are dicts carrying at least: id, camera, name, ctime, emb (np float32), plus the
measurement fields axis_scores() reads.
"""
import numpy as np

from pipeline.score import photo_overall

GROUP_BY_CAMERA = True
GROUP_GAP_SECONDS = 2.0
GROUP_SIM = 0.92
GROUP_SIM_STRONG = 0.97
GROUP_GAP_STRONG = 8.0
POSE_TOL = 0.22


def subject_moved(a, b):
    if a["offset"] is None or b["offset"] is None:
        return False
    d = (abs(a["offset"] - b["offset"])
         + abs((a["face_cy"] or 0) - (b["face_cy"] or 0))
         + 1.5 * abs(a["face_frac"] - b["face_frac"])
         + 0.5 * abs(a["frontal"] - b["frontal"]))
    return d > POSE_TOL


def build_groups(records, refs):
    """Return list of groups (each a list of records), ordered best-first by avg overall."""
    cams: dict = {}
    for r in records:
        key = r["camera"] if GROUP_BY_CAMERA else "all"
        cams.setdefault(key, []).append(r)

    groups = []
    for recs in cams.values():
        chrono = sorted(recs, key=lambda r: (r["ctime"] if r["ctime"] is not None else 0.0, r["name"]))
        cur = []
        for r in chrono:
            if not cur:
                cur = [r]
                continue
            prev = cur[-1]
            ta = r["ctime"] if r["ctime"] is not None else 0.0
            tb = prev["ctime"] if prev["ctime"] is not None else 0.0
            gap = ta - tb
            sim = float(np.asarray(r["emb"]) @ np.asarray(prev["emb"]))
            same = ((gap <= GROUP_GAP_SECONDS and sim >= GROUP_SIM) or
                    (sim >= GROUP_SIM_STRONG and gap <= GROUP_GAP_STRONG))
            if same and subject_moved(r, prev):
                same = False
            if same:
                cur.append(r)
            else:
                groups.append(cur)
                cur = [r]
        if cur:
            groups.append(cur)

    def avg(g):
        return sum(photo_overall(r, refs) for r in g) / len(g)

    groups.sort(key=lambda g: (-avg(g), g[0]["ctime"] if g[0]["ctime"] is not None else 0.0))
    return groups
