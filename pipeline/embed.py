"""CLIP embeddings + expression scores + aesthetic head + image/EXIF loading.

EXIF helpers take a PIL Exif object (not a path) so the worker can read metadata straight
from downloaded bytes. Lifted from cull_server.py.
"""
import datetime
import io

import numpy as np
import torch
from PIL import Image, ImageFile, ImageOps

from pipeline import models

ImageFile.LOAD_TRUNCATED_IMAGES = True


def load_rgb_bytes(data: bytes) -> Image.Image:
    """Correctly-oriented RGB PIL image from raw bytes (e.g. a downloaded Gallera JPEG)."""
    pil = Image.open(io.BytesIO(data))
    pil = ImageOps.exif_transpose(pil)
    return pil.convert("RGB")


def clip_embed(images):
    """L2-normalized CLIP embeddings (numpy) for a list of PIL images, batched."""
    model, pre, _, dev = models.clip()
    out = []
    B = 32
    for k in range(0, len(images), B):
        batch = torch.stack([pre(im) for im in images[k:k + B]]).to(dev)
        with torch.no_grad():
            feats = model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        out.append(feats.cpu().numpy())
    return np.concatenate(out, axis=0) if out else np.zeros((0, 512), dtype="float32")


def clip_face_scores(crop):
    """Coarse expression scores in [0,1] for a face-crop PIL image: {smile, gaze}."""
    model, pre, _, dev = models.clip()
    text = models.expr_text()
    with torch.no_grad():
        im = pre(crop).unsqueeze(0).to(dev)
        e = model.encode_image(im)
        e = e / e.norm(dim=-1, keepdim=True)
        return {k: float((100 * e @ t.T).softmax(dim=-1)[0, 0]) for k, t in text.items()}


def aesthetic_score(emb):
    """LAION aesthetic mean-opinion ~1..10 from an L2-normalized CLIP embedding, or None."""
    head = models.aes_head()
    if head is None:
        return None
    with torch.no_grad():
        e = torch.from_numpy(np.asarray(emb, dtype="float32")).unsqueeze(0)
        e = e / e.norm(dim=-1, keepdim=True)
        return float(head(e)[0, 0])


def capture_time(exif) -> float | None:
    """EXIF DateTimeOriginal (+ sub-second) as epoch seconds, or None."""
    try:
        sub = exif.get_ifd(0x8769)        # ExifIFD
        dto = sub.get(0x9003)             # DateTimeOriginal
        if dto:
            t = datetime.datetime.strptime(dto, "%Y:%m:%d %H:%M:%S")
            frac = sub.get(0x9291)        # SubsecTimeOriginal
            if frac:
                try:
                    t += datetime.timedelta(seconds=float("0." + str(frac).strip()))
                except ValueError:
                    pass
            return t.timestamp()
    except Exception:
        pass
    return None


def camera_id(exif, filename: str) -> str:
    """Camera BODY id (so two bodies' shots never group together): EXIF serial > model >
    filename prefix (e.g. '068A1039.jpg' -> 'name:068A')."""
    try:
        sub = exif.get_ifd(0x8769)
        serial = sub.get(0xA431)          # BodySerialNumber
        if serial:
            return f"serial:{str(serial).strip()}"
        model = exif.get(0x0110)          # Model
        if model:
            return f"model:{str(model).strip()}"
    except Exception:
        pass
    stem = filename.rsplit(".", 1)[0]
    prefix = stem.rstrip("0123456789") or stem
    return f"name:{prefix}"
