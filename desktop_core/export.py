"""Export keepers back to the ORIGINAL files (the core "go straight to editing" hand-off).

Phase 1 is editor-agnostic: copy (default) or move the original RAW/JPEG of every favorite/maybe
pick into one **flat** destination — no per-label subfolders, no score report. Non-destructive by
default (originals are copied; the source folder is left untouched unless the caller asks to move).

Deluxe editor-specific output (XMP ratings/labels, Lightroom flags, Capture One sessions) is
Phase 2; this module exposes a single `export_to_folder` / `export_to_zip` seam those adapters
will plug into.
"""
from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path

from .store import CullStore

# Decision states that get exported; delete/none are skipped.
_EXPORT_STATES = {"favorite", "maybe"}


def _add_to_zip(zf: zipfile.ZipFile, src: Path, arc: str, when_ts: float | None = None) -> None:
    """Add `src` to the zip as `arc`, timestamped by the photo's CAPTURE time when known.

    The file's filesystem mtime is unreliable (the test RAWs carry a bogus 1979 mtime), so prefer
    the EXIF capture time (`when_ts`) and fall back to the mtime. The ZIP DOS timestamp can only
    encode years 1980-2107, so anything outside that window — a pre-1980 mtime, or a corrupt /
    far-future EXIF clock — is clamped to 1980-01-01 rather than crashing the whole export
    (`zipfile` raises on dates it can't pack). `localtime` itself can choke on absurd epochs, so it's
    guarded too. Streams the file (no full-file read)."""
    ts = when_ts if when_ts else src.stat().st_mtime
    try:
        dt = time.localtime(ts)[:6]
    except (OSError, ValueError, OverflowError):
        dt = None
    if not dt or not (1980 <= dt[0] <= 2107):
        dt = (1980, 1, 1, 0, 0, 0)
    info = zipfile.ZipInfo(arc, date_time=dt)
    info.compress_type = zipfile.ZIP_STORED
    with src.open("rb") as fsrc, zf.open(info, "w") as fdst:
        shutil.copyfileobj(fsrc, fdst)


def _picks(store: CullStore, sid: str) -> list[dict]:
    """Photo rows for every favorite/maybe pick, ordered by filename (deterministic output)."""
    states = store.current_states(sid)
    photos = {p["id"]: p for p in store.list_photos(sid)}
    picks = [photos[pid] for pid, st in states.items() if st in _EXPORT_STATES and pid in photos]
    picks.sort(key=lambda p: p["filename"].lower())
    return picks


def _unique(dest_dir: Path, name: str) -> Path:
    """Avoid clobbering when two picks share a filename."""
    target = dest_dir / name
    if not target.exists():
        return target
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while (dest_dir / f"{stem}_{i}{suffix}").exists():
        i += 1
    return dest_dir / f"{stem}_{i}{suffix}"


def export_to_folder(store: CullStore, sid: str, dest: str | Path, move: bool = False) -> dict:
    """Copy (default) or move every favorite/maybe original into one flat `dest` folder."""
    picks = _picks(store, sid)
    if not picks:
        raise ValueError("nothing to export — no favorite/maybe picks")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    exported = missing = 0
    for photo in picks:
        src = Path(photo["original_path"])
        if not src.exists():
            missing += 1
            continue
        target = _unique(dest, src.name)
        if move:
            shutil.move(str(src), str(target))
        else:
            shutil.copy2(str(src), str(target))
        exported += 1
    return {"dest": str(dest), "moved": move, "exported": exported, "missing": missing}


def export_to_zip(store: CullStore, sid: str, zip_path: str | Path) -> dict:
    """Bundle every favorite/maybe original, flat, into a zip (always non-destructive)."""
    picks = _picks(store, sid)
    if not picks:
        raise ValueError("nothing to export — no favorite/maybe picks")

    zip_path = Path(zip_path)
    exported = missing = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        seen: set[str] = set()
        for photo in picks:
            src = Path(photo["original_path"])
            if not src.exists():
                missing += 1
                continue
            arc = src.name
            n = 1
            while arc in seen:
                arc = f"{src.stem}_{n}{src.suffix}"
                n += 1
            seen.add(arc)
            _add_to_zip(zf, src, arc, photo.get("ctime"))
            exported += 1
    return {"zip": str(zip_path), "exported": exported, "missing": missing}
