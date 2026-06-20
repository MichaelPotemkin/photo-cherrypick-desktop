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


def test_export_nothing_raises(tmp_store, tmp_path):
    sid = tmp_store.create_session(str(tmp_path))  # no decisions
    with pytest.raises(ValueError):
        export_mod.export_to_folder(tmp_store, sid, tmp_path / "out")
