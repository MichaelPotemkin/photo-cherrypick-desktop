"""Feed-layout planner — arranges the keepers into a balanced Instagram/gallery sequence.

The photographer's "РАСПОЛОЖЕНИЕ КАДРОВ" ask: a feed reads best when shot SCALE alternates (a tight
portrait next to a wide/environmental frame, not three close-ups in a row) and SCENES are spread out
(the same look doesn't clump three-in-a-row). This is a greedy ordering over the favorites that, at
each step, picks the remaining frame with the most contrast against what was just placed — a
different scale AND a different-looking scene — with a light quality tiebreak. The result is a
deterministic, pleasing sequence the photographer can lay straight into a 3-wide grid.

Pure function (no store / no torch) so it's unit-testable.
"""
from __future__ import annotations

import numpy as np

# Weights for the greedy "what goes next" score.
_W_SCALE = 1.0    # reward a different shot scale than the previous frame
_W_SCENE = 1.3    # reward a scene that doesn't look like the last 1-2 frames (spread looks out)
_W_QUAL = 0.3     # light tiebreak toward the stronger frame


def shot_scale(rec: dict) -> str:
    """Shot scale from how much of the frame the face fills: close-up / medium / wide(+environmental).

    Keys off face_frac. `n_faces == 0` (a detector ran and found nobody) forces wide; but an ABSENT
    n_faces (analyses predating that field) is unknown, so we fall back to face_frac, which they have.
    """
    ff = rec.get("face_frac") or 0.0
    if rec.get("n_faces") == 0 or ff < 0.08:
        return "wide"
    if ff >= 0.18:
        return "close"
    return "medium"


def _cos(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


def plan_feed(records: list[dict]) -> list[dict]:
    """Reorder `records` (dicts with id, emb, face_frac, n_faces, overall) into feed order.

    Opens on the strongest frame, then greedily alternates scale and spreads scenes. ≤2 items just
    sort by quality. Does not mutate the input dicts.
    """
    pool = list(records)
    if len(pool) <= 2:
        return sorted(pool, key=lambda r: -(r.get("overall") or 0.0))

    scale = {id(r): shot_scale(r) for r in pool}
    order = [max(pool, key=lambda r: r.get("overall") or 0.0)]
    pool.remove(order[0])

    while pool:
        prev, prev2 = order[-1], (order[-2] if len(order) >= 2 else None)

        def next_score(c, prev=prev, prev2=prev2):
            scale_contrast = 1.0 if scale[id(c)] != scale[id(prev)] else 0.0
            sim = _cos(c.get("emb"), prev.get("emb"))
            if prev2 is not None:
                sim = max(sim, 0.6 * _cos(c.get("emb"), prev2.get("emb")))
            scene_contrast = 1.0 - sim
            return _W_SCALE * scale_contrast + _W_SCENE * scene_contrast + _W_QUAL * (c.get("overall") or 0.0)

        nxt = max(pool, key=next_score)
        order.append(nxt)
        pool.remove(nxt)
    return order
