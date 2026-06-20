"""Regression tests for the scoring improvements (see docs/SCORING-ITERATION-LOG.md):
eye-occlusion gate, saturating sharpness, and the occlusion-aware blink penalty."""
from pipeline.score import _sat, axis_scores, compute_refs
from pipeline.select import rank_burst
from tests.conftest import make_meta


def test_sat_diminishing_returns():
    assert _sat(0.0) == 0.0
    assert abs(_sat(0.25) - 0.5) < 1e-9      # quarter sharpness -> half score (lifts low end)
    assert abs(_sat(1.0) - 1.0) < 1e-9
    assert _sat(0.49) > 0.49                  # concave: compresses the top, lifts the middle


def test_saturation_lifts_focus_axis():
    # default scoring has SHARP_SAT on; a moderately-sharp frame's focus axis should be LIFTED
    # above the raw linear sharp/REF ratio (diminishing returns), not crushed.
    soft = make_meta(name="soft", eye_sharp=300.0)
    others = [make_meta(name=f"o{i}", eye_sharp=v) for i, v in enumerate([800, 1200, 1600, 2000])]
    refs = compute_refs([soft] + others)
    axes = axis_scores(soft, refs)[0]
    linear = min(1.0, 300.0 / refs["eye"])
    assert axes["eye sharpness"] >= linear
    if linear < 1.0:
        assert axes["eye sharpness"] > linear   # sqrt lifts values below the reference


def test_occlusion_ignores_eye_signals():
    # two occluded frames differing ONLY in eye sharpness + eye-open count -> scores ~equal
    a = make_meta(name="a", eyes_occluded=True, eyes=2, eye_sharp=2000.0)
    b = make_meta(name="b", eyes_occluded=True, eyes=0, eye_sharp=100.0)
    refs = compute_refs([a, b])
    oa, ob = axis_scores(a, refs)[2], axis_scores(b, refs)[2]
    assert abs(oa - ob) < 0.02
    reasons = axis_scores(a, refs)[3]
    assert "eyes open" not in reasons and "sharp eyes" not in reasons
    assert any("sunglasses" in r for r in reasons)


def test_occlusion_decides_on_smile():
    a = make_meta(name="a", eyes_occluded=True, smile=0.9)
    b = make_meta(name="b", eyes_occluded=True, smile=0.1)
    refs = compute_refs([a, b])
    assert axis_scores(a, refs)[2] > axis_scores(b, refs)[2]   # eyes hidden -> expression decides


def test_blink_penalty_only_when_eyes_visible():
    # eyes visible: the open-eyed frame beats a marginally sharper blink
    a = make_meta(name="open", eyes=2, eye_sharp=300.0)
    b = make_meta(name="blink", eyes=0, eye_sharp=340.0)
    refs = compute_refs([a, b])
    assert rank_burst([a, b], refs)[0] == 0

    # eyes occluded: eyes==0 is sunglasses, NOT a blink -> no penalty; smile decides
    c = make_meta(name="occ_lo", eyes=2, eyes_occluded=True, smile=0.1)
    d = make_meta(name="occ_smile", eyes=0, eyes_occluded=True, smile=0.9)
    refs2 = compute_refs([c, d])
    assert rank_burst([c, d], refs2)[0] == 1   # d (smiling) wins, not blink-demoted


def _face(eyes=2, smile=0.8, gaze=0.8, occ=False):
    return {"eyes": eyes, "smile": smile, "gaze": gaze, "eyes_occluded": occ}


def test_group_subject_penalizes_a_blinking_second_face():
    # Two family frames identical except the 2nd subject blinks in one. The all-eyes-open frame
    # must win on the subject category — the single-largest-face scorer was blind to this.
    base = dict(eyes=2, smile=0.8, gaze=0.8)
    both_open = make_meta(name="both", faces=[_face(), _face()], **base)
    one_blink = make_meta(name="blink", faces=[_face(), _face(eyes=0)], **base)
    refs = compute_refs([both_open, one_blink])
    s_both = axis_scores(both_open, refs)[1]["subject"]
    s_blink = axis_scores(one_blink, refs)[1]["subject"]
    assert s_both > s_blink + 0.1                       # the blink clearly drags the group down
    assert axis_scores(both_open, refs)[2] > axis_scores(one_blink, refs)[2]
    assert "all eyes open" in axis_scores(both_open, refs)[3]
    assert "all eyes open" not in axis_scores(one_blink, refs)[3]


def test_solo_subject_unchanged_by_group_logic():
    # A single-face meta (no "faces" list -> fallback) scores subject by the legacy formula.
    m = make_meta(name="solo", eyes=2, smile=0.8, gaze=0.8)
    refs = compute_refs([m])
    legacy = 0.45 * 1.0 + 0.40 * 0.8 + 0.15 * 0.8
    assert abs(axis_scores(m, refs)[1]["subject"] - legacy) < 1e-9
