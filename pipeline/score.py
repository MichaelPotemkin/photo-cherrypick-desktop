"""Multi-axis scoring. Lifted from cull_server.py; the cross-photo reference percentiles
(FOCUS_REF, EYE_REF, ...) are now an explicit `refs` dict computed per session via
compute_refs(), instead of module globals."""
import math
import os

import numpy as np

# saturating sharpness (diminishing returns past "acceptably sharp") — validated +2 vs the
# reference panel, so it's the default now; SHARP_SAT=0 restores the legacy linear behaviour.
_SHARP_SAT = os.environ.get("SHARP_SAT", "1") == "1"


def _sat(x):
    """Diminishing-returns transform: once a frame is acceptably sharp, extra sharpness adds little.
    sqrt lifts the low-mid and compresses the top (0.25->0.5, 0.49->0.7, 0.81->0.9, 1->1)."""
    return _clamp01(math.sqrt(_clamp01(x)))

# Subject + focus dominate (a portrait lives or dies on a sharp-eyed, open-eyed, well-
# expressed subject); exposure/composition matter; aesthetic + color are lighter & neutral.
CAT_WEIGHTS = {"focus": 0.28, "subject": 0.29, "composition": 0.16,
               "exposure": 0.13, "aesthetic": 0.06, "color": 0.08}
# the LAION aesthetic head is noisy and reacts to colour grade more than subject quality, so it
# was over-flipping near-ties; shrink each value toward 0.5 to cap its tie-breaking power.
AES_SHRINK = 0.6

# TODO (subject-aware scoring): these axes + weights were tuned/validated ONLY on a single
# MALE-subject session, so they assume one notion of "good". Criteria differ by subject and
# genre (female / mixed / group / non-portrait). Path forward: validate on female + mixed
# datasets; move to subject-conditioned PROFILES (detect subject or let the user pick) rather
# than one global weight set; re-tune the CLIP expression prompts + composition priors per
# profile; keep weights data-driven. See also the group-photos TODO in pipeline/faces.py.


def _clamp01(v):
    return max(0.0, min(1.0, float(v)))


def _gauss(x, mu, sig):
    return math.exp(-((x - mu) ** 2) / (2 * sig * sig))


def compute_refs(metas) -> dict:
    """Robust 90th-percentile references over a session's measurement dicts."""
    faced = [m for m in metas if m.get("offset") is not None]
    aes = [m["aesthetic"] for m in metas if m.get("aesthetic") is not None]
    return {
        "focus": float(np.percentile([m["face_sharp"] for m in faced], 90)) if faced else 1.0,
        "eye": float(np.percentile([m["eye_sharp"] for m in faced], 90)) if faced else 1.0,
        "sharp": float(np.percentile([m["sharp"] for m in metas], 90)) if metas else 1.0,
        "clutter": float(np.percentile([m["clutter"] for m in metas], 90)) if metas else 0.1,
        "aes_lo": float(np.percentile(aes, 10)) if len(aes) > 4 else 4.0,
        "aes_hi": float(np.percentile(aes, 90)) if len(aes) > 4 else 7.0,
    }


def axis_scores(r, refs):
    """(axes, cats, overall, reasons). Artistic choices (B&W, side-light, shallow DoF) are
    not penalized; real disqualifiers (blink, soft eyes, blown face, bad crop) drive it down."""
    FOCUS_REF, EYE_REF, SHARP_REF = refs["focus"], refs["eye"], refs["sharp"]
    CLUTTER_REF, AES_LO, AES_HI = refs["clutter"], refs["aes_lo"], refs["aes_hi"]

    faced = r["offset"] is not None
    # eyes hidden behind sunglasses (or otherwise not visible): eye-open count + eye-sharpness +
    # eye-contact are noise, so drop them and lean on face sharpness / expression / pose instead.
    occluded = faced and bool(r.get("eyes_occluded"))
    # Per-face subject signals (couple/family). Falls back to a single face synthesized from the
    # top-level fields for old analyses / synthetic test metas, so solo scoring is unchanged.
    flist = (r.get("faces") if faced else None) or (
        [{"eyes": r["eyes"], "smile": r["smile"], "gaze": r["gaze"], "eyes_occluded": occluded}]
        if faced else [])
    group = len(flist) > 1
    eye_f = face_f = sep = eyes_s = 0.0
    head = size = 0.5
    level = 1.0 - min(1.0, abs(r["roll"]) / 30.0)
    clean = _clamp01(1.0 - r["clutter"] / (CLUTTER_REF + 1e-6))

    if faced:
        _sharp = _sat if _SHARP_SAT else _clamp01
        eye_f = _sharp(r["eye_sharp"] / EYE_REF) if EYE_REF > 0 else 0.0
        face_f = _sharp(r["face_sharp"] / FOCUS_REF) if FOCUS_REF > 0 else 0.0
        sep = _clamp01(r["sep"])
        if occluded:
            focus = 0.7 * face_f + 0.3 * sep            # no eye-sharpness term
        else:
            focus = 0.5 * eye_f + 0.35 * face_f + 0.15 * sep
    else:
        focus = _clamp01(r["sharp"] / SHARP_REF) if SHARP_REF > 0 else 0.0

    expo_mean = _gauss(r["exp_mean"], 0.48, 0.20)
    clip_pen = _clamp01(1.0 - 6.0 * (r["clip_hi"] + r["clip_lo"]))
    exposure = _clamp01(0.6 * expo_mean + 0.4 * clip_pen)

    def _face_subject(f):
        es = 1.0 if f.get("eyes", 0) >= 2 else (0.5 if f.get("eyes", 0) == 1 else 0.0)
        if f.get("eyes_occluded"):
            # eyes hidden: drop the (corrupted) eye-open count; judge engagement by mouth-smile +
            # CLIP camera-gaze (geometric `frontal` and a CLIP facing/eyes-open probe both tested
            # net-neutral-or-worse on the audit shoot — see docs/SCORING-ITERATION-LOG.md).
            return 0.7 * f.get("smile", 0.0) + 0.3 * f.get("gaze", 0.0)
        return 0.45 * es + 0.40 * f.get("smile", 0.0) + 0.15 * f.get("gaze", 0.0)

    if faced:
        s = [_face_subject(f) for f in flist]
        # Group-aware fold: reward everyone looking good (mean) AND penalize the worst subject
        # (min) — a blinking or looking-away child tanks the frame even if the adults are perfect.
        # One face => mean == min, so a solo portrait scores exactly as before.
        subject = 0.5 * (sum(s) / len(s)) + 0.5 * min(s)
        # axis-display aggregates (mean across faces; equal the primary value when solo)
        vis = [f for f in flist if not f.get("eyes_occluded")] or flist
        eyes_s = sum(1.0 if f.get("eyes", 0) >= 2 else (0.5 if f.get("eyes", 0) == 1 else 0.0)
                     for f in vis) / len(vis)
        smile_disp = sum(f.get("smile", 0.0) for f in flist) / len(flist)
        gaze_disp = sum(f.get("gaze", 0.0) for f in flist) / len(flist)
    else:
        subject = 0.0
        smile_disp, gaze_disp = r["smile"], r["gaze"]

    if faced:
        head = _clamp01(1.0 - abs(r["face_top"] - 0.09) / 0.25)
        ff = r["face_frac"]
        size = 1.0 if 0.06 <= ff <= 0.45 else (ff / 0.06 if ff < 0.06 else _clamp01(1.0 - (ff - 0.45) / 0.45))
        composition = 0.30 * r["thirds"] + 0.25 * head + 0.20 * size + 0.15 * level + 0.10 * clean
    else:
        composition = 0.5 * clean + 0.5 * level

    catch = 1.0 if r["catch"] else 0.0
    even = _clamp01(1.0 - (r["evenness"] - 1.0) / 3.0)
    neutral = _clamp01(1.0 - r["cast"] / 30.0)
    contrast_ok = _gauss(r["contrast"], 0.22, 0.12)
    color = 0.35 * contrast_ok + 0.25 * neutral + 0.20 * even + 0.20 * catch

    if r.get("aesthetic") is not None and AES_HI > AES_LO:
        aes_raw = _clamp01((r["aesthetic"] - AES_LO) / (AES_HI - AES_LO))
        aesthetic = _clamp01(0.5 + AES_SHRINK * (aes_raw - 0.5))   # damp extremes toward 0.5
    else:
        aesthetic = 0.5

    cats = {"focus": focus, "exposure": exposure, "subject": subject,
            "composition": composition, "color": color, "aesthetic": aesthetic}
    if faced:
        overall = sum(cats[k] * CAT_WEIGHTS[k] for k in CAT_WEIGHTS)
    else:
        w = {k: (0.0 if k == "subject" else v) for k, v in CAT_WEIGHTS.items()}
        tot = sum(w.values())
        overall = 0.5 * sum(cats[k] * w[k] for k in w) / tot

    reasons = []
    # eye-based reasons are meaningless when the eyes aren't visible — suppress them if occluded.
    # For a group, a reason only fires when it holds for EVERYONE (all eyes open / everyone smiling).
    vis = [f for f in flist if not f.get("eyes_occluded")]
    if faced and vis and all(f.get("eyes", 0) >= 2 for f in vis):
        reasons.append("all eyes open" if group else "eyes open")
    if not occluded and eye_f >= 0.85:
        reasons.append("sharp eyes")
    if faced and (min(f.get("smile", 0.0) for f in flist) if group else r["smile"]) >= 0.6:
        reasons.append("everyone smiling" if group else "smiling")
    if faced and not occluded and r["frontal"] >= 0.6 and gaze_disp >= 0.65:
        reasons.append("eye contact")
    if exposure >= 0.85 and r["clip_hi"] < 0.02:
        reasons.append("well exposed")
    if faced and not occluded and catch:
        reasons.append("catchlight")
    if occluded:
        reasons.append("sunglasses — judged on pose & expression")

    axes = {"eye sharpness": eye_f, "face sharpness": face_f, "subject vs bg": sep,
            "exposure": exposure, "contrast": contrast_ok,
            "eyes open": eyes_s, "expression": smile_disp, "eye contact": gaze_disp,
            "rule of thirds": r["thirds"] if faced else 0.5, "headroom": head,
            "framing/size": size, "clean bg": clean, "aesthetic": aesthetic}
    return axes, cats, _clamp01(overall), reasons


def photo_overall(r, refs):
    return axis_scores(r, refs)[2]
