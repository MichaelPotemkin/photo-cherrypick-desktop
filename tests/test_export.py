import datetime
import os
import time
import zipfile
from pathlib import Path

import pytest

from desktop_core import export as export_mod
from tests.conftest import write_jpeg


def _seed(store, src_dir: Path):
    """Three real files on disk; mark one favorite, one maybe, one delete."""
    sid = store.create_session(str(src_dir))
    files = {}
    for name in ("fav.jpg", "maybe.jpg", "trash.jpg"):
        p = write_jpeg(src_dir / name)
        pid = store.add_photo(sid, name, str(p), is_raw=False)
        store.save_analysis(pid, emb=None, meta={}, axes={"exposure": 0.9}, cats={"focus": 0.8},
                            overall=0.7, reasons=[], group_idx=0, in_group_order=0, suggested=False)
        files[name] = pid
    store.set_total(sid, 3)
    store.add_decision(sid, files["fav.jpg"], "favorite")
    store.add_decision(sid, files["maybe.jpg"], "maybe")
    store.add_decision(sid, files["trash.jpg"], "delete")
    return sid


def test_export_to_folder_is_flat_and_nondestructive(tmp_store, tmp_path):
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    dest = tmp_path / "out"

    res = export_mod.export_to_folder(tmp_store, sid, dest, move=False)
    assert res["exported"] == 2 and res["missing"] == 0

    # flat: favorite + maybe land directly in dest, no subfolders, no report.csv
    assert (dest / "fav.jpg").exists()
    assert (dest / "maybe.jpg").exists()
    assert not (dest / "trash.jpg").exists()          # delete excluded
    assert not (dest / "favorites").exists() and not (dest / "maybe").exists()
    assert not (dest / "report.csv").exists()

    # originals untouched (copy, not move)
    assert (src / "fav.jpg").exists() and (src / "maybe.jpg").exists() and (src / "trash.jpg").exists()


def test_export_to_zip_is_flat(tmp_store, tmp_path):
    sid = _seed(tmp_store, tmp_path / "src")
    zpath = tmp_path / "picks.zip"
    export_mod.export_to_zip(tmp_store, sid, zpath)
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
    assert names == {"fav.jpg", "maybe.jpg"}          # flat, no subfolders, no report.csv


def test_export_to_zip_handles_pre_1980_mtime(tmp_store, tmp_path):
    # ZIP can't encode timestamps before 1980; a RAW with a 1979 mtime used to crash the export.
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    pre_1980 = time.mktime((1979, 11, 30, 12, 0, 0, 0, 0, -1))
    os.utime(src / "fav.jpg", (pre_1980, pre_1980))

    zpath = tmp_path / "picks.zip"
    res = export_mod.export_to_zip(tmp_store, sid, zpath)   # must NOT raise
    assert res["exported"] == 2
    with zipfile.ZipFile(zpath) as zf:
        assert set(zf.namelist()) == {"fav.jpg", "maybe.jpg"}
        assert zf.getinfo("fav.jpg").date_time[0] >= 1980   # clamped to a valid year


def test_export_to_zip_clamps_out_of_range_capture_time(tmp_store, tmp_path):
    # ZIP DOS dates only span 1980-2107; a corrupt/far-future EXIF clock must NOT crash the export
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    future = datetime.datetime(3000, 1, 1).timestamp()   # year 3000 — outside the ZIP window
    pid = next(p["id"] for p in tmp_store.list_photos(sid) if p["filename"] == "fav.jpg")
    tmp_store._conn.execute("UPDATE photos SET ctime=? WHERE id=?", (future, pid))
    tmp_store._conn.commit()

    zpath = tmp_path / "picks.zip"
    res = export_mod.export_to_zip(tmp_store, sid, zpath)   # must NOT raise struct.error
    assert res["exported"] == 2
    with zipfile.ZipFile(zpath) as zf:
        assert 1980 <= zf.getinfo("fav.jpg").date_time[0] <= 2107   # clamped into range


def test_export_zip_timestamps_by_capture_time(tmp_store, tmp_path):
    # the real EXIF capture time wins over the (here bogus 1979) filesystem mtime
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    pre_1980 = time.mktime((1979, 11, 30, 12, 0, 0, 0, 0, -1))
    os.utime(src / "fav.jpg", (pre_1980, pre_1980))
    capture = datetime.datetime(2023, 8, 20, 18, 9, 12).timestamp()
    pid = next(p["id"] for p in tmp_store.list_photos(sid) if p["filename"] == "fav.jpg")
    tmp_store._conn.execute("UPDATE photos SET ctime=? WHERE id=?", (capture, pid))
    tmp_store._conn.commit()

    zpath = tmp_path / "picks.zip"
    export_mod.export_to_zip(tmp_store, sid, zpath)
    with zipfile.ZipFile(zpath) as zf:
        assert zf.getinfo("fav.jpg").date_time[:3] == (2023, 8, 20)   # capture time, not the 1980 clamp


def test_export_nothing_raises(tmp_store, tmp_path):
    sid = tmp_store.create_session(str(tmp_path))  # no decisions
    with pytest.raises(ValueError):
        export_mod.export_to_folder(tmp_store, sid, tmp_path / "out")
