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


def _greedy_order(pool: list[dict], scale: dict) -> list[dict]:
    """Open on the strongest frame, then at each step take the remaining frame with the most contrast
    (different scale AND a different-looking scene) against the last 1-2 placed, light quality tiebreak."""
    pool = list(pool)
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


def _sim_lookup(records: list[dict]):
    """Precompute the pairwise cosine-similarity matrix once (rows are L2-normalised embeddings) and
    return a fast `sim(a, b)` keyed by record identity. Missing/zero embeddings read as similarity 0."""
    ids = {id(r): k for k, r in enumerate(records)}
    dim = next((np.asarray(r["emb"]).ravel().shape[0] for r in records if r.get("emb") is not None), 0)
    mat = np.zeros((len(records), dim or 1), dtype=np.float32)
    for k, r in enumerate(records):
        e = r.get("emb")
        if e is not None:
            v = np.asarray(e, dtype=np.float32).ravel()
            nrm = float(np.linalg.norm(v))
            if nrm > 0 and v.shape[0] == mat.shape[1]:
                mat[k] = v / nrm
    gram = mat @ mat.T
    return lambda a, b: float(gram[ids[id(a)], ids[id(b)]])


def _adjacency_cost(order: list[dict]) -> float:
    """The cost the smoothing pass minimises: a penalty per adjacent pair for sharing a shot scale and
    for looking alike. Lower = a more varied sequence. Self-contained (recomputes scale/sim) for tests."""
    scale = {id(r): shot_scale(r) for r in order}
    sim = _sim_lookup(order)
    return sum(
        (_W_SCALE if scale[id(a)] == scale[id(b)] else 0.0) + _W_SCENE * sim(a, b)
        for a, b in zip(order, order[1:])
    )


def _smooth(order: list[dict], scale: dict, sim) -> list[dict]:
    """2-opt-style local improvement over the greedy order: repeatedly apply the swap that lowers the
    adjacency cost (same-scale + look-alike neighbours), keeping the strong opener fixed at index 0.
    Smooths the tail the single greedy pass leaves clumped once the pool empties (issue #5). Each
    accepted swap strictly lowers the total via the touched edges, so it converges; the pass cap is a
    safety bound. O(n²) candidates × O(1) edge cost per pass — well within a one-shot feed-view call."""
    n = len(order)
    pos = list(order)

    def ecost(a, b):
        return (_W_SCALE if scale[id(a)] == scale[id(b)] else 0.0) + _W_SCENE * sim(a, b)

    improved, guard = True, 0
    while improved and guard < n:
        improved, guard = False, guard + 1
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                edges = {k for k in (i - 1, i, j - 1, j) if 0 <= k < n - 1}
                before = sum(ecost(pos[k], pos[k + 1]) for k in edges)
                pos[i], pos[j] = pos[j], pos[i]
                after = sum(ecost(pos[k], pos[k + 1]) for k in edges)
                if after >= before - 1e-9:
                    pos[i], pos[j] = pos[j], pos[i]   # no gain — revert
                else:
                    improved = True
    return pos


def plan_feed(records: list[dict]) -> list[dict]:
    """Reorder `records` (dicts with id, emb, face_frac, n_faces, overall) into feed order.

    Opens on the strongest frame and greedily alternates scale / spreads scenes, then runs a 2-opt
    local-improvement pass to smooth the tail (which a single greedy pass leaves clumped as the pool
    empties — issue #5). ≤2 items just sort by quality. Does not mutate the input dicts.
    """
    pool = list(records)
    if len(pool) <= 2:
        return sorted(pool, key=lambda r: -(r.get("overall") or 0.0))

    scale = {id(r): shot_scale(r) for r in pool}
    order = _greedy_order(pool, scale)
    return _smooth(order, scale, _sim_lookup(pool))
