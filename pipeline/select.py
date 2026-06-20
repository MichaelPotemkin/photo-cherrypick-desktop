"""In-burst pick logic — the single source of truth for which frame in a group is "suggested".

Used by both the production worker (desktop_core/pipeline_runner) and the offline eval harness
so that scoring experiments measure exactly what ships.
"""
from pipeline.score import axis_scores

BLINK_PENALTY = 0.15


def _rank_value(m, refs):
    return axis_scores(m, refs)[2]


def rank_burst(metas, refs):
    """Return indices of `metas` ordered best-first for the in-burst pick.

    Demotes a likely blink (eyes==0 while open-eyed siblings exist) — but NOT when the eyes are
    occluded (sunglasses read as 'eyes closed' must not be treated as a blink).
    """
    def usable_eyes(m):
        return m.get("offset") is not None and not m.get("eyes_occluded")

    has_open = any(usable_eyes(m) and m.get("eyes", 0) >= 2 for m in metas)

    def key(i):
        m = metas[i]
        ov = _rank_value(m, refs)
        if has_open and usable_eyes(m) and m.get("eyes", 0) == 0:
            ov -= BLINK_PENALTY
        return ov

    return sorted(range(len(metas)), key=key, reverse=True)
