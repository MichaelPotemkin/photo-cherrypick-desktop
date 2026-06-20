"""Pure-numpy checks on the reused pipeline scoring/grouping (no torch models executed)."""
import numpy as np

from pipeline.group import build_groups
from pipeline.scene_group import build_scene_groups
from pipeline.score import axis_scores, compute_refs
from tests.conftest import _unit_emb, make_meta


def test_overall_in_unit_range_and_faceless_capped():
    recs = [make_meta(name="a.jpg"), make_meta(name="b.jpg", faced=False)]
    refs = compute_refs(recs)
    for r in recs:
        _axes, _cats, overall, _reasons = axis_scores(r, refs)
        assert 0.0 <= overall <= 1.0
    # a faceless photo can score at most 0.5 (subject weight zeroed + halved)
    assert axis_scores(recs[1], refs)[2] <= 0.5


def test_burst_groups_by_similarity_and_time():
    e1 = make_meta(name="x")["emb"]              # shared embedding -> sim 1.0
    e2 = np.roll(e1, 7)                          # different vector -> low sim
    recs = [
        make_meta(name="a.jpg", emb=e1, ctime=1000.0),
        make_meta(name="b.jpg", emb=e1, ctime=1001.0),   # within 2s + identical -> same burst
        make_meta(name="c.jpg", emb=e2, ctime=5000.0),   # far + dissimilar -> own group
    ]
    refs = compute_refs(recs)
    groups = build_groups(recs, refs)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]
    burst = max(groups, key=len)
    assert {r["name"] for r in burst} == {"a.jpg", "b.jpg"}


def test_pose_change_splits_a_burst():
    e1 = make_meta(name="x")["emb"]
    a = make_meta(name="a.jpg", emb=e1, ctime=1000.0, offset=0.1, face_cy=0.45, face_frac=0.12)
    b = make_meta(name="b.jpg", emb=e1, ctime=1001.0, offset=0.9, face_cy=0.9, face_frac=0.4)  # moved
    groups = build_groups([a, b], compute_refs([a, b]))
    assert sorted(len(g) for g in groups) == [1, 1]  # pose change forces a split


def test_scene_groups_merge_same_look_across_time_and_split_outfits():
    """Scene mode clusters by appearance only — same look merges however far apart in time, and a
    different outfit (near-orthogonal embedding) splits off, unlike burst's tight time gate. (The
    threshold is applied in mean-centered space, where orthogonal looks become ~antipodal.)"""
    a = _unit_emb(1)          # "look A" direction
    b = _unit_emb(2)          # "look B" — a random unit vector is ~orthogonal to A (cos ≈ 0)
    recs = [
        {"id": "a1", "emb": a, "ctime": 1000.0, "overall": 0.7},
        {"id": "b1", "emb": b, "ctime": 1005.0, "overall": 0.6},
        {"id": "a2", "emb": a, "ctime": 9000.0, "overall": 0.9},  # same look, hours later
    ]
    groups = build_scene_groups(recs, sim_threshold=0.55)
    assert sorted(len(g) for g in groups) == [1, 2]
    scene_a = max(groups, key=len)
    assert {r["id"] for r in scene_a} == {"a1", "a2"}   # merged despite the large time gap
    assert [r["id"] for r in scene_a] == ["a2", "a1"]   # members ordered best-first by overall
    assert len(groups[0]) == 2                          # highest-avg scene comes first


def test_scene_threshold_keeps_distinct_looks_apart():
    """Below-threshold similarity must not merge: three mutually-dissimilar looks (a, an a/b blend,
    and b) each stay in their own scene rather than chaining together."""
    a = _unit_emb(3)
    b = _unit_emb(4)
    blend = a + b
    blend = blend / np.linalg.norm(blend)              # ~0.71 raw cosine to each of a, b
    recs = [
        {"id": "a", "emb": a, "ctime": 1.0, "overall": 0.5},
        {"id": "mix", "emb": blend, "ctime": 2.0, "overall": 0.5},
        {"id": "b", "emb": b, "ctime": 3.0, "overall": 0.5},
    ]
    groups = build_scene_groups(recs, sim_threshold=0.55)
    assert sorted(len(g) for g in groups) == [1, 1, 1]  # no chaining across the gap


def test_scene_duplicates_merge_not_fragment():
    """Regression: identical embeddings (or frames at the set centroid) must NOT each become their
    own singleton. Full mean-centering would collapse them to the zero vector → noise direction →
    spurious singletons; the mean-shrinkage keeps their raw direction so they merge into one scene."""
    dup = _unit_emb(5)
    recs = [{"id": f"d{i}", "emb": dup, "ctime": float(i), "overall": 0.5} for i in range(4)]
    groups = build_scene_groups(recs, sim_threshold=0.55)
    assert len(groups) == 1 and len(groups[0]) == 4  # all four land in one scene
