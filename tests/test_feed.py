"""Unit tests for the feed-layout planner (pure ordering logic, no store/torch)."""
import numpy as np

from desktop_core.feed import plan_feed, shot_scale


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
