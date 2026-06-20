"""Face detection + per-face metrics. Lifted from cull_server.py; models come from pipeline.models.

See the group-photos TODO in detect_face (single-subject limitation) and the subject-aware
TODO at the scoring weights in pipeline/score.py.
"""
import math
import os

import cv2
import numpy as np

from pipeline import models
from pipeline.metrics import exposure_metrics, lapvar

# Down-scale cap before face detection. Raised 1024 -> 1920: small/distant faces (a child set back
# from the couple) become detectable without lowering the confidence threshold. 1920 beat 2560 on
# the audit (the model degrades past it). Env-tunable. See docs/SCORING-ITERATION-LOG.md.
DETECT_MAX = int(os.environ.get("DETECT_MAX", "1920"))
FACE_NORM = 256   # face crops are resized to this height before eye/sharpness analysis


# A face smaller than this fraction of the LARGEST face's area is treated as a background
# bystander, not a subject — so it doesn't drag a couple/family frame's group score down.
FACE_REL_MIN = 0.15
MAX_FACES = 4   # score at most the N largest faces (bounds cost on big group shots)


def detect_faces(rgb, w, h, max_faces: int = MAX_FACES, rel_min: float = FACE_REL_MIN):
    """All prominent faces as [((x, y, fw, fh), landmarks), ...], largest first.

    Closes the group-photo gap: couple/family shots get every subject's face, so scoring can
    aggregate (a frame is a reject if ANY subject blinks/looks away). Background bystanders —
    faces below `rel_min` × the largest face's area — are dropped; the list is capped at
    `max_faces`. A solo shot returns a single face, so downstream behaviour is unchanged.
    See the subject-aware (female/mixed) note in pipeline/score.py."""
    raw: list[tuple] = []
    yunet = models.yunet()
    if yunet is not None:
        scale = min(1.0, DETECT_MAX / max(w, h))
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if scale < 1.0:
            bgr = cv2.resize(bgr, (sw, sh))
        yunet.setInputSize((sw, sh))
        _, faces = yunet.detect(bgr)
        if faces is not None and len(faces):
            inv = 1.0 / scale
            for f in faces:
                box = (f[0] * inv, f[1] * inv, f[2] * inv, f[3] * inv)
                lms = {"reye": (f[4] * inv, f[5] * inv),
                       "leye": (f[6] * inv, f[7] * inv),
                       "nose": (f[8] * inv, f[9] * inv)}
                raw.append((box, lms))
    else:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        for f in models.haar().detectMultiScale(gray, 1.1, 5, minSize=(60, 60)):
            raw.append((tuple(float(v) for v in f), None))
    if not raw:
        return []
    raw.sort(key=lambda bl: bl[0][2] * bl[0][3], reverse=True)
    biggest = raw[0][0][2] * raw[0][0][3]
    return [bl for bl in raw if bl[0][2] * bl[0][3] >= rel_min * biggest][:max_faces]


def detect_face(rgb, w, h):
    """Largest face as ((x, y, fw, fh), landmarks), or (None, None). Back-compat wrapper around
    detect_faces (which is the group-aware entry point)."""
    faces = detect_faces(rgb, w, h, max_faces=1)
    return faces[0] if faces else (None, None)


def eye_open_count(gray, box):
    """How many open eyes Haar finds in the upper face (0/1/2). Confident 2 => eyes open;
    lower is ambiguous (blink, sunglasses, profile). Positive-only signal."""
    x, y, w, h = (int(round(v)) for v in box)
    x0, y0 = max(0, x), max(0, y)
    region = gray[y0:y0 + int(h * 0.62), x0:min(gray.shape[1], x + w)]
    if region.size == 0:
        return 0
    m = max(12, int(w * 0.12))
    eyes = models.eye_cascade().detectMultiScale(region, 1.1, 6, minSize=(m, m))
    return min(2, len(eyes))


def head_pose(lms):
    """(roll degrees, frontal 0..1) from eye/nose landmarks. frontal~1 faces camera."""
    reye, leye, nose = lms["reye"], lms["leye"], lms["nose"]
    roll = float(math.degrees(math.atan2(leye[1] - reye[1], leye[0] - reye[0])))
    dl, dr = abs(nose[0] - leye[0]), abs(nose[0] - reye[0])
    frontal = float(min(dl, dr) / max(dl, dr)) if max(dl, dr) > 1e-6 else 1.0
    return roll, frontal


def face_region_metrics(pil_full, box_w, lms_w, w_work, h_work):
    """Eyes/sharpness/catchlight/face-exposure on a SIZE-NORMALIZED crop from the full-res
    image (Haar eye detection is scale-finicky; normalizing every face to FACE_NORM px makes
    these resolution-independent). Returns a dict or None."""
    wf, hf = pil_full.size
    sx, sy = wf / w_work, hf / h_work
    x, y, fw, fh = box_w
    X, Y, FW, FH = x * sx, y * sy, fw * sx, fh * sy
    m = 0.3 * FW
    cx0, cy0 = max(0, int(X - m)), max(0, int(Y - m))
    cx1, cy1 = min(wf, int(X + FW + m)), min(hf, int(Y + FH + m))
    crop = pil_full.crop((cx0, cy0, cx1, cy1))
    if crop.height < 8 or crop.width < 8:
        return None
    sc = FACE_NORM / crop.height
    crop = crop.resize((max(1, int(crop.width * sc)), FACE_NORM))
    cg = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2GRAY)
    Ch, Cw = cg.shape
    fx0, fy0 = int((X - cx0) * sc), int((Y - cy0) * sc)
    fw_n, fh_n = int(FW * sc), int(FH * sc)
    nx0, ny0 = max(0, fx0), max(0, fy0)
    nx1, ny1 = min(Cw, fx0 + fw_n), min(Ch, fy0 + fh_n)
    fcrop = cg[ny0:ny1, nx0:nx1]
    face_sharp = lapvar(fcrop) if fcrop.size > 16 else 0.0
    f_mean, f_hi, f_lo = exposure_metrics(fcrop) if fcrop.size else (None, 0.0, 0.0)
    if fcrop.size and fcrop.shape[1] >= 2:
        half = fcrop.shape[1] // 2
        lft, rgt = fcrop[:, :half].mean(), fcrop[:, half:].mean()
        evenness = float(max(lft, rgt) / (min(lft, rgt) + 1e-6))
    else:
        evenness = 1.0
    eyes = eye_open_count(cg, (fx0, fy0, fw_n, fh_n))
    eye_sharp, catch = 0.0, 0
    if lms_w:
        pts = {k: ((lms_w[k][0] * sx - cx0) * sc, (lms_w[k][1] * sy - cy0) * sc)
               for k in ("reye", "leye")}
        iod = abs(pts["leye"][0] - pts["reye"][0])
        r = max(4, int(iod * 0.22))
        patches = []
        for k in ("reye", "leye"):
            ex, ey = int(pts[k][0]), int(pts[k][1])
            patches.append(cg[max(0, ey - r):min(Ch, ey + r), max(0, ex - r):min(Cw, ex + r)])
        eye_sharp = max((lapvar(p) for p in patches if p.size > 16), default=0.0)
        catch = max((1 if (p.size >= 16 and 0.003 < (p >= 230).mean() < 0.25) else 0)
                    for p in patches)
    return {"face_sharp": face_sharp, "eye_sharp": eye_sharp, "eyes": int(eyes),
            "catch": int(catch), "evenness": evenness,
            "f_mean": f_mean, "f_hi": f_hi, "f_lo": f_lo}
