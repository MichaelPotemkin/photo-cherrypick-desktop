"""Local-folder ingest — replaces the Gallera URL parser as the primary entry path.

Scans a folder for images, pairs RAW+JPEG shot together (same stem) into a single item, and
decides which file to *load* (preview/EXIF) vs which to treat as the *original* for export.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .raw_preview import JPEG_EXTS, OTHER_IMAGE_EXTS, RAW_EXTS, is_image


@dataclass
class FileItem:
    filename: str        # name of the original (what the photographer sees)
    original_path: str   # file to copy on export (the RAW if shot RAW) — never modified
    load_path: str       # file to load for preview/analysis (prefer a sidecar JPEG for EXIF)
    is_raw: bool


def _pick(paths: list[Path], exts: set[str]) -> Path | None:
    for p in sorted(paths):
        if p.suffix.lower() in exts:
            return p
    return None


def scan_folder(folder: str | Path, recursive: bool = True) -> list[FileItem]:
    """Return one FileItem per distinct stem, pairing a RAW with its JPEG sidecar."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))

    walker = folder.rglob("*") if recursive else folder.glob("*")
    by_stem: dict[tuple[str, str], list[Path]] = {}
    for p in walker:
        if not p.is_file() or not is_image(p):
            continue
        # skip hidden files AND anything inside a hidden directory (.Trashes, .Spotlight-V100,
        # .cache, …) — checking only the leaf name would let those system files through.
        if any(part.startswith(".") for part in p.relative_to(folder).parts):
            continue
        # key on parent + lowercase stem so IMG_001.CR3 and IMG_001.JPG pair, but
        # identically-named files in different subfolders stay distinct.
        by_stem.setdefault((str(p.parent), p.stem.lower()), []).append(p)

    items: list[FileItem] = []
    for paths in by_stem.values():
        raw = _pick(paths, RAW_EXTS)
        jpg = _pick(paths, JPEG_EXTS)
        other = _pick(paths, OTHER_IMAGE_EXTS)
        original = raw or jpg or other
        load = jpg or other or raw  # prefer a directly-readable file for EXIF + speed
        if original is None or load is None:
            continue
        items.append(
            FileItem(
                filename=original.name,
                original_path=str(original),
                load_path=str(load),
                is_raw=original.suffix.lower() in RAW_EXTS,
            )
        )
    # stable, photographer-friendly order
    items.sort(key=lambda it: it.filename.lower())
    return items
