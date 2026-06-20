"""Unit tests for the feed-layout planner (pure ordering logic, no store/torch)."""
import numpy as np

from desktop_core.feed import _adjacency_cost, _greedy_order, plan_feed, shot_scale


def rec(rid, emb, ff=0.15, nf=1, ov=0.7):
    return {"id": rid, "emb": np.array(emb, dtype=np.float32), "face_frac": ff, "n_faces": nf, "overall": ov}


def test_shot_scale_buckets():
    assert shot_scale(rec("a", [1], ff=0.30, nf=1)) == "close"
    assert shot_scale(rec("a", [1], ff=0.15, nf=1)) == "medium"
    assert shot_scale(rec("a", [1], ff=0.02, nf=1)) == "wide"
    assert shot_scale(rec("a", [1], ff=0.30, nf=0)) == "wide"   # no face -> environmental/wide


def test_plan_feed_is_a_permutation():
    recs = [rec(str(i), [1 if i == j else 0 for j in range(6)], ov=0.5 + 0.01 * i) for i in range(6)]
    out = plan_feed(recs)
    assert sorted(r["id"] for r in out) == sorted(r["id"] for r in recs)


def test_plan_feed_opens_on_strongest():
    recs = [rec("a", [1, 0], ov=0.5), rec("b", [0, 1], ov=0.95), rec("c", [1, 1], ov=0.6)]
    # 3 items -> greedy; opener is the highest-overall frame
    assert plan_feed(recs)[0]["id"] == "b"


def test_plan_feed_spreads_duplicate_scenes():
    # two near-identical scenes (same embedding) must not end up adjacent
    e1, e2, e3 = [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]
    recs = [rec("a1", e1, ov=0.9), rec("a2", e1, ov=0.8), rec("b", e2, ov=0.7), rec("c", e3, ov=0.6)]
    out = [r["id"] for r in plan_feed(recs)]
    assert abs(out.index("a1") - out.index("a2")) >= 2


def test_plan_feed_alternates_scale():
    close = [rec(f"c{i}", [1, 0], ff=0.30, nf=1) for i in range(3)]
    wide = [rec(f"w{i}", [0, 1], ff=0.0, nf=0) for i in range(3)]
    scales = [shot_scale(r) for r in plan_feed(close + wide)]
    assert not any(scales[i] == scales[i + 1] == scales[i + 2] for i in range(len(scales) - 2))


def test_small_input_sorts_by_quality():
    out = plan_feed([rec("a", [1, 0], ov=0.4), rec("b", [0, 1], ov=0.9)])
    assert [r["id"] for r in out] == ["b", "a"]


def _runs3(order):
    """How many 3-in-a-row same-scale windows the sequence has (the issue-#5 symptom)."""
    s = [shot_scale(r) for r in order]
    return sum(1 for i in range(len(s) - 2) if s[i] == s[i + 1] == s[i + 2])


def test_smoothing_never_worsens_and_actually_helps():
    # An unbalanced pool (7 close-ups, 4 wides) the single greedy pass tends to clump toward the tail.
    # Across seeds the 2-opt post-pass must never raise the adjacency cost (it's a local improvement),
    # and on at least one layout it strictly lowers it — i.e. it does real work.
    improved_any = False
    for seed in range(8):
        rng = np.random.default_rng(seed)
        recs = [rec(f"c{i}", rng.standard_normal(8), ff=0.30, nf=1, ov=float(rng.random())) for i in range(7)]
        recs += [rec(f"w{i}", rng.standard_normal(8), ff=0.0, nf=0, ov=float(rng.random())) for i in range(4)]
        scale = {id(r): shot_scale(r) for r in recs}
        greedy = _greedy_order(recs, scale)
        smoothed = plan_feed(recs)
        cg, cs = _adjacency_cost(greedy), _adjacency_cost(smoothed)
        assert cs <= cg + 1e-6                                          # never worse than greedy
        assert sorted(r["id"] for r in smoothed) == sorted(r["id"] for r in recs)  # still a permutation
        assert smoothed[0]["id"] == greedy[0]["id"]                     # strong opener preserved
        if cs < cg - 1e-6:
            improved_any = True
    assert improved_any


def test_smoothing_reduces_tail_clumps_on_adversarial_layout():
    # Wides whose embeddings the greedy front-loads (so it spends them early and clumps closes at the
    # tail); a global 2-opt swap can interleave a wide back into the tail and cut the 3-in-a-row runs.
    rng = np.random.default_rng(3)
    recs = [rec(f"c{i}", rng.standard_normal(8), ff=0.30, nf=1, ov=0.6) for i in range(8)]
    recs += [rec(f"w{i}", rng.standard_normal(8), ff=0.0, nf=0, ov=0.9) for i in range(3)]
    scale = {id(r): shot_scale(r) for r in recs}
    assert _runs3(plan_feed(recs)) <= _runs3(_greedy_order(recs, scale))


def test_plan_feed_is_deterministic():
    recs = [rec(str(i), np.random.default_rng(i).standard_normal(8), ff=0.3 if i % 2 else 0.0,
                nf=1 if i % 2 else 0, ov=0.5 + 0.01 * i) for i in range(9)]
    assert [r["id"] for r in plan_feed(recs)] == [r["id"] for r in plan_feed(recs)]
