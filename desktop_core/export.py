"""Export keepers back to the ORIGINAL files (the core "go straight to editing" hand-off).

Copy (default) or move the original RAW/JPEG of every favorite/maybe pick into one **flat**
destination — no per-label subfolders, no score report. Non-destructive by default (originals are
copied; the source folder is left untouched unless the caller asks to move).

Alongside each picked original we write a Lightroom-style **XMP sidecar** (`DSC1234.NEF` ->
`DSC1234.xmp`) carrying a star rating + colour label, so the cull travels into the editor: favorites
land as 5 stars / Green, maybes as 3 stars / Yellow. Lightroom (and Bridge / Camera Raw) auto-detect
the sidecar on import; the originals stay byte-identical. RAW is the intended target — for JPEG the
editor may prefer embedded metadata over a sidecar, but the file is still written (harmless, and many
tools honour it). Pass `write_xmp=False` to skip the sidecars entirely.
"""
from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .store import CullStore

# Decision states that get exported; delete/none are skipped.
_EXPORT_STATES = {"favorite", "maybe"}

# Decision -> (xmp:Rating stars, xmp:Label colour). Lightroom shows both natively, so favorite vs
# maybe is distinguishable at a glance in the Library grid.
_XMP_BY_STATE = {
    "favorite": (5, "Green"),
    "maybe": (3, "Yellow"),
}


def _xmp_sidecar(rating: int, label: str) -> bytes:
    """A minimal, valid XMP packet carrying just the star rating + colour label.

    This is the standard sidecar Lightroom/Bridge read for proprietary RAW: a tiny RDF document with
    `xmp:Rating` (0-5) and `xmp:Label`. We keep it deliberately small — develop settings, flags, etc.
    stay the editor's job. `escape` guards the label even though our values are fixed today."""
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">\n'
        f"   <xmp:Rating>{int(rating)}</xmp:Rating>\n"
        f"   <xmp:Label>{escape(label)}</xmp:Label>\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>\n'
    ).encode("utf-8")


def _zip_date(ts: float | None) -> tuple[int, int, int, int, int, int]:
    """A ZIP DOS date_time (year clamped to 1980-2107) from an epoch, never raising.

    ZIP can only encode years 1980-2107, so a pre-1980 mtime or a corrupt/far-future EXIF clock is
    clamped to 1980-01-01 rather than crashing the export (`zipfile` raises on dates it can't pack).
    `localtime` itself can choke on absurd epochs, so it's guarded too."""
    try:
        dt = time.localtime(ts)[:6] if ts else None
    except (OSError, ValueError, OverflowError):
        dt = None
    if not dt or not (1980 <= dt[0] <= 2107):
        dt = (1980, 1, 1, 0, 0, 0)
    return dt


def _add_to_zip(zf: zipfile.ZipFile, src: Path, arc: str, when_ts: float | None = None) -> None:
    """Add `src` to the zip as `arc`, timestamped by the photo's CAPTURE time when known.

    The file's filesystem mtime is unreliable (the test RAWs carry a bogus 1979 mtime), so prefer
    the EXIF capture time (`when_ts`) and fall back to the mtime. Streams the file (no full-file
    read)."""
    ts = when_ts if when_ts else src.stat().st_mtime
    info = zipfile.ZipInfo(arc, date_time=_zip_date(ts))
    info.compress_type = zipfile.ZIP_STORED
    with src.open("rb") as fsrc, zf.open(info, "w") as fdst:
        shutil.copyfileobj(fsrc, fdst)


def _picks(store: CullStore, sid: str) -> list[dict]:
    """Photo rows for every favorite/maybe pick, ordered by filename (deterministic output).

    Each returned row carries an extra `_state` key (favorite/maybe) so the writer can pick the
    right XMP rating without re-querying."""
    states = store.current_states(sid)
    photos = {p["id"]: p for p in store.list_photos(sid)}
    picks = [
        {**photos[pid], "_state": st}
        for pid, st in states.items()
        if st in _EXPORT_STATES and pid in photos
    ]
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


def export_to_folder(
    store: CullStore, sid: str, dest: str | Path, move: bool = False, write_xmp: bool = True
) -> dict:
    """Copy (default) or move every favorite/maybe original into one flat `dest` folder.

    When `write_xmp`, drop a Lightroom sidecar next to each exported original (see module docstring).
    Sidecars are always copies — `move` only relocates the photo, never the rating file."""
    picks = _picks(store, sid)
    if not picks:
        raise ValueError("nothing to export — no favorite/maybe picks")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    exported = missing = xmp = 0
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
        if write_xmp:
            # Lightroom's convention: same basename, .xmp extension. A raw+jpeg pair shares a
            # basename, so guard against clobbering the first sidecar.
            side = _unique(dest, target.with_suffix(".xmp").name)
            rating, label = _XMP_BY_STATE[photo["_state"]]
            side.write_bytes(_xmp_sidecar(rating, label))
            xmp += 1
    return {"dest": str(dest), "moved": move, "exported": exported, "missing": missing, "xmp": xmp}


def export_to_zip(store: CullStore, sid: str, zip_path: str | Path, write_xmp: bool = True) -> dict:
    """Bundle every favorite/maybe original, flat, into a zip (always non-destructive).

    When `write_xmp`, each original is followed by its `.xmp` sidecar entry (same basename),
    timestamped to match the photo so the pair sorts together."""
    picks = _picks(store, sid)
    if not picks:
        raise ValueError("nothing to export — no favorite/maybe picks")

    zip_path = Path(zip_path)
    exported = missing = xmp = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        seen: set[str] = set()

        def _claim(name: str) -> str:
            arc, stem, suffix, n = name, Path(name).stem, Path(name).suffix, 1
            while arc in seen:
                arc = f"{stem}_{n}{suffix}"
                n += 1
            seen.add(arc)
            return arc

        for photo in picks:
            src = Path(photo["original_path"])
            if not src.exists():
                missing += 1
                continue
            ts = photo.get("ctime") or src.stat().st_mtime
            arc = _claim(src.name)
            _add_to_zip(zf, src, arc, ts)
            exported += 1
            if write_xmp:
                rating, label = _XMP_BY_STATE[photo["_state"]]
                info = zipfile.ZipInfo(_claim(Path(arc).with_suffix(".xmp").name), date_time=_zip_date(ts))
                zf.writestr(info, _xmp_sidecar(rating, label))
                xmp += 1
    return {"zip": str(zip_path), "exported": exported, "missing": missing, "xmp": xmp}
