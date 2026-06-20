"""Preview-first image loading for the desktop culler.

Per the Phase-1 PRD: we do NOT develop RAW sensor data for culling. Every RAW file embeds a
full-size JPEG preview; we extract that (camera-agnostic, fast, how Photo Mechanic culls). Only
if no usable embedded preview exists do we fall back to a full rawpy decode. Regular images
(JPEG/PNG/HEIC-as-jpeg/TIFF) load directly. Anything we can't render returns None so the caller
can show a clear "unsupported" state instead of crashing.

True RAW *develop* is intentionally out of scope — that's the editor's job, and we hand the
original file off untouched.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

# RAW containers we recognise by extension. Detection is trivial and never blocks; whether a
# given body *renders* depends on libraw (rawpy) — handled by the preview-first + fallback chain.
RAW_EXTS = {
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".sr2", ".srf", ".raf", ".orf",
    ".rw2", ".pef", ".dng", ".raw", ".rwl", ".dcr", ".kdc", ".mrw", ".x3f", ".3fr",
    ".mef", ".iiq", ".mos", ".erf", ".gpr", ".braw",
}
JPEG_EXTS = {".jpg", ".jpeg", ".jpe", ".jfif"}
OTHER_IMAGE_EXTS = {".png", ".tif", ".tiff", ".webp", ".bmp", ".heic", ".heif"}

IMAGE_EXTS = RAW_EXTS | JPEG_EXTS | OTHER_IMAGE_EXTS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def is_raw(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTS


def _raw_embedded_preview(path: Path) -> Image.Image | None:
    """Extract the embedded full-size preview from a RAW file (preview-first). None if absent."""
    try:
        import rawpy
    except ImportError:
        return None
    try:
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
    except Exception:
        return None
    try:
        if thumb.format == rawpy.ThumbFormat.JPEG:
            # embedded preview JPEGs carry their own EXIF Orientation — honour it so portrait
            # RAWs aren't analysed/displayed sideways (matches the non-RAW path)
            return ImageOps.exif_transpose(Image.open(io.BytesIO(thumb.data))).convert("RGB")
        # BITMAP: thumb.data is an HxWx3 ndarray (already oriented by libraw; no EXIF to apply)
        return Image.fromarray(thumb.data).convert("RGB")
    except Exception:
        return None


def _raw_full_decode(path: Path) -> Image.Image | None:
    """Last resort: actually develop the RAW (slow). Used only if no embedded preview."""
    try:
        import numpy as np
        import rawpy
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        return Image.fromarray(np.ascontiguousarray(rgb)).convert("RGB")
    except Exception:
        return None


def load_rgb(path: Path) -> Image.Image | None:
    """Return an RGB PIL image suitable for analysis/preview, or None if unrenderable.

    RAW  -> embedded preview, then full decode.
    Else -> direct PIL open (HEIC needs pillow-heif registered; falls through to None if missing).
    """
    path = Path(path)
    if is_raw(path):
        return _raw_embedded_preview(path) or _raw_full_decode(path)
    try:
        img = Image.open(path)
        # honour EXIF orientation so the displayed/analysed pixels match what the camera intended
        return ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return None


def make_thumbnail(img: Image.Image, max_side: int = 1024) -> Image.Image:
    """Downscale a copy to fit within max_side (for fast UI display / caching)."""
    thumb = img.copy()
    thumb.thumbnail((max_side, max_side), Image.LANCZOS)
    return thumb
