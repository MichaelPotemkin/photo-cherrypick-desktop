"""Per-photo multi-axis analysis. Pure function: PIL image in -> measurement dict out.

Lifted from cull_server.py's analyze(), minus the disk cache and prior-reuse (the DB owns
persistence now). Whole-frame metrics run on a WORK_EDGE working image; per-face metrics on
a size-normalized crop from the full-res image.
"""
import math

import cv2
import numpy as np
from PIL import Image

from pipeline.embed import aesthetic_score, clip_embed, clip_face_scores
from pipeline.faces import detect_faces, eye_open_count, face_region_metrics, head_pose
from pipeline.metrics import (
    colorfulness,
    contrast_rms,
    dynamic_range,
    exposure_metrics,
    lapvar,
    wb_cast,
)

WORK_EDGE = 1024
# above this CLIP zero-shot "sunglasses" score, treat the eyes as not visible (occluded)
SUNGLASSES_T = 0.6


def _clamp01(v):
    return max(0.0, min(1.0, float(v)))


def _subject_metrics(pil, rgb, gray, box, lms, W, H) -> dict:
    """Per-face subject signals score.py aggregates across a group: eyes-open, smile, gaze, frontal
    pose, eye/face sharpness, face size, sunglasses occlusion. Same computations the primary-face
    block does, packaged per face so a blinking/averted secondary subject can lower the frame."""
    x, y, fw, fh = (int(round(v)) for v in box)
    _, frontal = head_pose(lms) if lms else (0.0, 1.0)
    fm = face_region_metrics(pil, box, lms, W, H)
    if fm:
        face_sharp, eye_sharp, eyes = fm["face_sharp"], fm["eye_sharp"], fm["eyes"]
    else:
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + fw), min(H, y + fh)
        fcw = gray[y0:y1, x0:x1]
        face_sharp, eye_sharp, eyes = (lapvar(fcw) if fcw.size > 16 else 0.0), 0.0, 0
    eyes = max(eyes, eye_open_count(gray, (x, y, fw, fh)))
    mx, my = int(fw * 0.5), int(fh * 0.5)
    fc = Image.fromarray(rgb[max(0, y - my):min(H, y + fh + my),
                             max(0, x - mx):min(W, x + fw + mx)])
    expr = clip_face_scores(fc)
    return {
        "eyes": int(eyes), "smile": float(expr["smile"]), "gaze": float(expr["gaze"]),
        "frontal": float(frontal), "eye_sharp": float(eye_sharp), "face_sharp": float(face_sharp),
        "face_frac": _clamp01(fw / W),
        "eyes_occluded": bool(expr.get("sunglasses", 0.0) >= SUNGLASSES_T),
    }


def analyze(pil: Image.Image, ctime: float | None = None) -> dict:
    """Return the full measurement dict for one photo (includes 'emb' as a numpy array)."""
    work = pil.copy()
    work.thumbnail((WORK_EDGE, WORK_EDGE))
    rgb = np.asarray(work)
    W, H = work.size
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160) > 0

    sharp = lapvar(gray)
    g_mean, g_hi, g_lo = exposure_metrics(gray)
    contrast = contrast_rms(gray)
    dyn = dynamic_range(gray)
    color = colorfulness(rgb)
    is_bw = color < 5.0
    cast = wb_cast(rgb)
    cs = max(8, min(H, W) // 4)
    bg_sharp = float(np.median([lapvar(gray[a:b, c:d]) for a, b, c, d in
                                ((0, cs, 0, cs), (0, cs, W - cs, W),
                                 (H - cs, H, 0, cs), (H - cs, H, W - cs, W))]))

    all_faces = detect_faces(rgb, W, H)            # largest first; bystanders filtered (see faces.py)
    box, lms = all_faces[0] if all_faces else (None, None)
    if box is not None:
        x, y, fw, fh = (int(round(v)) for v in box)
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + fw), min(H, y + fh)
        offset = _clamp01((x + fw / 2) / W)
        face_frac = _clamp01(fw / W)
        face_cy = _clamp01((y + fh / 2) / H)
        face_top = _clamp01(y / H)
        roll, frontal = head_pose(lms) if lms else (0.0, 1.0)
        eye_y = _clamp01(((lms["reye"][1] + lms["leye"][1]) / 2) / H) if lms else face_cy
        thirds = math.exp(-((eye_y - 0.333) ** 2) / (2 * 0.10 ** 2))
        fcw = gray[y0:y1, x0:x1]
        fs_work = lapvar(fcw) if fcw.size > 16 else 0.0
        sep = _clamp01((math.log10(fs_work / (bg_sharp + 1e-6) + 1e-6) + 0.3) / 1.3)
        # clutter = background edge density: exclude EVERY subject's face box (group-aware)
        mask = np.ones_like(gray, dtype=bool)
        for (b, _l) in all_faces:
            bx, by, bw, bh = (int(round(v)) for v in b)
            mask[max(0, by):min(H, by + bh), max(0, bx):min(W, bx + bw)] = False
        clutter = float((edges & mask).sum() / max(1, mask.sum()))
        fm = face_region_metrics(pil, box, lms, W, H)
        if fm:
            face_sharp, eye_sharp = fm["face_sharp"], fm["eye_sharp"]
            eyes, catch, evenness = fm["eyes"], fm["catch"], fm["evenness"]
            exp_mean = fm["f_mean"] if fm["f_mean"] is not None else g_mean
            clip_hi, clip_lo = fm["f_hi"], fm["f_lo"]
        else:
            face_sharp, eye_sharp, eyes, catch, evenness = fs_work, 0.0, 0, 0, 1.0
            exp_mean, clip_hi, clip_lo = g_mean, g_hi, g_lo
        eyes = max(eyes, eye_open_count(gray, (x, y, fw, fh)))   # OR across scales for recall
        mx, my = int(fw * 0.5), int(fh * 0.5)
        fc = Image.fromarray(rgb[max(0, y - my):min(H, y + fh + my),
                                 max(0, x - mx):min(W, x + fw + mx)])
        expr = clip_face_scores(fc)
        smile, gaze = expr["smile"], expr["gaze"]
        sunglasses = expr.get("sunglasses", 0.0)
        # per-face subject signals for group scoring: the primary face reuses what we just computed;
        # any additional subjects (couple/family) are measured the same way.
        primary_face = {
            "eyes": int(eyes), "smile": float(smile), "gaze": float(gaze), "frontal": float(frontal),
            "eye_sharp": float(eye_sharp), "face_sharp": float(face_sharp), "face_frac": face_frac,
            "eyes_occluded": bool(sunglasses >= SUNGLASSES_T),
        }
        faces = [primary_face] + [_subject_metrics(pil, rgb, gray, b, lm, W, H)
                                  for (b, lm) in all_faces[1:]]
    else:
        offset = face_cy = face_top = None
        face_frac = face_sharp = eye_sharp = thirds = sep = 0.0
        eyes, roll, frontal, catch = 0, 0.0, 0.0, 0
        evenness = 1.0
        exp_mean, clip_hi, clip_lo = g_mean, g_hi, g_lo
        clutter = float(edges.mean())
        smile, gaze, sunglasses = 0.0, 0.0, 0.0
        faces = []

    small = pil.copy()
    small.thumbnail((256, 256))
    emb = clip_embed([small])[0]

    return {
        "sharp": sharp, "face_sharp": face_sharp, "eye_sharp": eye_sharp, "sep": sep,
        "exp_mean": exp_mean, "clip_hi": clip_hi, "clip_lo": clip_lo,
        "contrast": contrast, "dyn": dyn, "color": color, "is_bw": bool(is_bw), "cast": cast,
        "evenness": evenness, "catch": int(catch),
        "offset": offset, "face_frac": face_frac, "face_cy": face_cy, "face_top": face_top,
        "roll": roll, "frontal": frontal, "eyes": int(eyes), "thirds": thirds, "clutter": clutter,
        "smile": smile, "gaze": gaze, "ctime": ctime,
        "sunglasses": float(sunglasses),
        "eyes_occluded": bool(box is not None and sunglasses >= SUNGLASSES_T),
        "n_faces": len(faces), "faces": faces,
        "aesthetic": aesthetic_score(emb),
        "emb": emb,
    }
