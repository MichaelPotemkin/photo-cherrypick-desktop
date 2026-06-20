"""Scene / outfit grouping — the *second-pass* counterpart to burst grouping (pipeline/group.py).

Burst grouping answers "which frames are near-duplicate shots of the same instant?" — it gates
hard on a tight time window so it only ever merges a rapid-fire burst. That's the first culling
pass.

Scene grouping answers a different question for the *second* pass, after culling: "of the keepers
I have left, which belong to the same look — same setting, same outfit?" Here time is NOT a gate
(a photographer revisits a backdrop or an outfit across a shoot), so we cluster purely by global
CLIP similarity, with a *looser* threshold than a burst. The result lets the photographer assemble
an Instagram carousel / gallery set scene-by-scene and pick the best one or two per look.

The algorithm is deliberately greedy (single online pass) rather than a full hierarchical
clustering: it's O(n·k), deterministic, has no K to choose, and — assigning each photo to its
*nearest existing cluster centroid* rather than to any single neighbour — resists the chaining that
sinks single-linkage when two distinct looks happen to share a transitional frame.

The one essential pre-step is **mean-centering**. For a single-subject shoot, raw CLIP embeddings
are crammed into a narrow high-cosine band (~0.72–0.87 on the audit shoot) because the same person
in the same studio dominates every vector — a raw global threshold can't separate looks (it lumps
the whole shoot into one cluster). Subtracting the session-mean embedding and re-normalizing strips
that shared component, so what's left is each frame's *deviation* — its outfit, backdrop, framing —
and cosine in that centered space (which spreads out to roughly −0.25..0.28) actually discriminates
scenes. Centering is over the exact set handed in, so it tracks the current keepers.

Records are dicts carrying at least: id, emb (np float32, L2-normalized), ctime, overall.
"""
import os

import numpy as np

# Cosine threshold in the **centered** space (see module docstring) — NOT raw CLIP cosine. After
# mean-centering, same-look frames sit well above this and different looks well below.
# Calibrated on the audit shoot: a 3-point vision-judge sweep (0.35/0.45/0.55) found cluster
# coherence rises monotonically to 0.88 at 0.55 (outlier rate 0.06), and 0.55 is also the
# fragmentation knee — past it singleton scenes explode (~35→64 on the keeper set) without buying
# coherence. See docs/SCORING-ITERATION-LOG.md. Tunable via env so the harness can sweep without edits.
SCENE_SIM = float(os.environ.get("SCENE_SIM", "0.55"))

# Subtract this *fraction* of the session mean rather than the whole mean. Full centering (1.0)
# has a degenerate failure: a frame at the set centroid — an exact/near duplicate of the average,
# or a duplicate group whose members ARE the mean — centers to the zero vector, whose normalized
# direction is pure noise, so it never matches any centroid and is forced into a spurious singleton.
# Shrinking to 0.95 leaves a tiny (1-α)·e component so such frames keep their raw direction and
# merge correctly, while the clustering on real (well-spread) keepers is essentially unchanged from
# full centering: on the audit shoot 0.95 vs 1.0 gives the same multi-scene structure, only folding
# ~3 spurious centroid-singletons back in. Env-tunable for the harness.
SCENE_CENTER = float(os.environ.get("SCENE_CENTER", "0.95"))


def _normalize(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _centered(records) -> dict:
    """id -> shrunk-mean-centered, re-normalized embedding for the given record set."""
    if not records:
        return {}
    E = np.stack([_normalize(r["emb"]) for r in records]).astype(np.float32)
    mean = E.mean(axis=0)
    out = {}
    for r, e in zip(records, E):
        out[r["id"]] = _normalize(e - SCENE_CENTER * mean)
    return out


def build_scene_groups(records, sim_threshold: float = SCENE_SIM):
    """Greedily cluster keeper photos into scenes/looks by mean-centered CLIP similarity.

    Returns a list of groups (each a list of the input records), clusters ordered best-first by
    average `overall`, and members within each cluster ordered best-first by `overall`.
    """
    cen = _centered(records)

    # Walk chronologically so a continuously-shot look accretes into one cluster; assignment is by
    # similarity to *all* existing centroids, so the same scene revisited later still merges in.
    chrono = sorted(
        records,
        key=lambda r: (r["ctime"] if r.get("ctime") is not None else 0.0, r.get("id", "")),
    )

    clusters: list[dict] = []  # each: {members: [...], sum: vec, centroid: unit vec}
    for r in chrono:
        emb = cen[r["id"]]
        best_i, best_sim = -1, -1.0
        for i, c in enumerate(clusters):
            sim = float(emb @ c["centroid"])
            if sim > best_sim:
                best_sim, best_i = sim, i
        if best_i >= 0 and best_sim >= sim_threshold:
            c = clusters[best_i]
            c["members"].append(r)
            c["sum"] = c["sum"] + emb
            c["centroid"] = _normalize(c["sum"])
        else:
            clusters.append({"members": [r], "sum": emb.copy(), "centroid": emb.copy()})

    groups = [c["members"] for c in clusters]

    def _ov(r) -> float:
        return float(r.get("overall") or 0.0)

    for g in groups:
        g.sort(key=_ov, reverse=True)

    def avg(g) -> float:
        return sum(_ov(r) for r in g) / len(g)

    groups.sort(key=lambda g: (-avg(g), g[0].get("ctime") or 0.0))
    return groups
