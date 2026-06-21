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
import sys
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
    except ImportError as e:
        # rawpy/libraw not bundled — RAW support is simply unavailable; expected on such builds.
        print(f"raw_preview: rawpy unavailable, cannot read {path.name}: {e}", file=sys.stderr)
        return None
    try:
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
    except Exception as e:
        # libraw raises a grab-bag of types (LibRawError subclasses, ValueError) and the "no
        # embedded thumb" case is normal — stay non-fatal so we fall through to a full decode, but
        # surface the reason (corrupt file, OOM, unsupported body all look identical otherwise).
        print(f"raw_preview: embedded-preview extract failed for {path.name}: {e!r}", file=sys.stderr)
        return None
    try:
        if thumb.format == rawpy.ThumbFormat.JPEG:
            # embedded preview JPEGs carry their own EXIF Orientation — honour it so portrait
            # RAWs aren't analysed/displayed sideways (matches the non-RAW path)
            return ImageOps.exif_transpose(Image.open(io.BytesIO(thumb.data))).convert("RGB")
        # BITMAP: thumb.data is an HxWx3 ndarray (already oriented by libraw; no EXIF to apply)
        return Image.fromarray(thumb.data).convert("RGB")
    except Exception as e:
        # decoding the extracted thumb (PIL / ndarray conversion) failed — non-fatal, fall through
        # to the full-decode path, but log so a systematically broken preview is diagnosable.
        print(f"raw_preview: embedded-preview decode failed for {path.name}: {e!r}", file=sys.stderr)
        return None


def raw_exif(path: Path):
    """EXIF read straight from a RAW file's embedded preview, as a PIL Exif object (or None).

    `load_rgb` returns developed RGB pixels that have lost their EXIF, so RAW capture time / camera
    body must be read here instead. The embedded preview JPEG carries the metadata."""
    try:
        import rawpy
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            return Image.open(io.BytesIO(thumb.data)).getexif()
    except Exception as e:
        # best-effort: missing rawpy, no embedded thumb, or an unreadable preview just means we
        # lose RAW capture time (caller copes with None) — non-fatal, but log so it's diagnosable.
        print(f"raw_preview: RAW EXIF read failed for {path.name}: {e!r}", file=sys.stderr)
        return None
    return None


def _raw_full_decode(path: Path) -> Image.Image | None:
    """Last resort: actually develop the RAW (slow). Used only if no embedded preview."""
    try:
        import numpy as np
        import rawpy
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        return Image.fromarray(np.ascontiguousarray(rgb)).convert("RGB")
    except Exception as e:
        # full develop is the last resort; failure here means the file is genuinely unrenderable
        # (corrupt, truly unsupported body) — or a preventable condition like MemoryError on a huge
        # frame. Stays non-fatal (caller marks it "unsupported"), but log so OOM/corruption don't
        # masquerade as plain "unsupported format".
        print(f"raw_preview: full RAW decode failed for {path.name}: {e!r}", file=sys.stderr)
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
    except Exception as e:
        # unidentifiable/corrupt image, or a missing decoder (e.g. pillow-heif not registered for
        # HEIC) — non-fatal so the caller can show "unsupported", but log so a missing plugin or a
        # corrupt file is distinguishable.
        print(f"raw_preview: image open failed for {path.name}: {e!r}", file=sys.stderr)
        return None


def make_thumbnail(img: Image.Image, max_side: int = 1024) -> Image.Image:
    """Downscale a copy to fit within max_side (for fast UI display / caching)."""
    thumb = img.copy()
    thumb.thumbnail((max_side, max_side), Image.LANCZOS)
    return thumb
