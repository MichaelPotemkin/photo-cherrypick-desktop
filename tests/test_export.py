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
    export_mod.export_to_zip(tmp_store, sid, zpath, write_xmp=False)
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
    res = export_mod.export_to_zip(tmp_store, sid, zpath, write_xmp=False)   # must NOT raise
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


def test_export_to_folder_move_is_destructive(tmp_store, tmp_path):
    """move=True relocates the picked originals (gone from src, present in dest); un-picked files stay."""
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    dest = tmp_path / "out"
    res = export_mod.export_to_folder(tmp_store, sid, dest, move=True)
    assert res["moved"] is True and res["exported"] == 2
    assert (dest / "fav.jpg").exists() and (dest / "maybe.jpg").exists()
    assert not (src / "fav.jpg").exists() and not (src / "maybe.jpg").exists()  # moved out
    assert (src / "trash.jpg").exists()  # un-picked original untouched


def test_export_counts_missing_originals(tmp_store, tmp_path):
    """A pick whose original vanished from disk is counted as missing, not a crash."""
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    (src / "fav.jpg").unlink()  # a favorite's original deleted out from under us
    res = export_mod.export_to_folder(tmp_store, sid, tmp_path / "out")
    assert res["exported"] == 1 and res["missing"] == 1  # maybe exported, fav missing


def test_export_disambiguates_duplicate_filenames(tmp_store, tmp_path):
    """Two picks sharing a basename must both land in the flat dest without clobbering each other."""
    src = tmp_path / "src"
    sid = tmp_store.create_session(str(src))
    for sub in ("a", "b"):
        p = write_jpeg(src / sub / "dup.jpg")
        pid = tmp_store.add_photo(sid, "dup.jpg", str(p), is_raw=False)
        tmp_store.save_analysis(pid, emb=None, meta={}, axes={}, cats={}, overall=0.7,
                                reasons=[], group_idx=0, in_group_order=0, suggested=False)
        tmp_store.add_decision(sid, pid, "favorite")
    dest = tmp_path / "out"
    res = export_mod.export_to_folder(tmp_store, sid, dest, write_xmp=False)
    assert res["exported"] == 2
    assert {p.name for p in dest.iterdir()} == {"dup.jpg", "dup_1.jpg"}  # collision disambiguated


# --- XMP sidecars (Lightroom hand-off) ---

def _rating_label(xmp: str) -> tuple[int, str]:
    """Pull (Rating, Label) out of a sidecar without a real XML parser (the packet is fixed-shape)."""
    rating = int(xmp.split("<xmp:Rating>")[1].split("</xmp:Rating>")[0])
    label = xmp.split("<xmp:Label>")[1].split("</xmp:Label>")[0]
    return rating, label


def test_export_folder_writes_xmp_sidecars(tmp_store, tmp_path):
    """One .xmp per pick, named by basename, with favorite=5/Green and maybe=3/Yellow."""
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    dest = tmp_path / "out"

    res = export_mod.export_to_folder(tmp_store, sid, dest)
    assert res["exported"] == 2 and res["xmp"] == 2

    assert (dest / "fav.xmp").exists() and (dest / "maybe.xmp").exists()
    assert _rating_label((dest / "fav.xmp").read_text()) == (5, "Green")     # favorite
    assert _rating_label((dest / "maybe.xmp").read_text()) == (3, "Yellow")  # maybe
    # the sidecar sits beside its original, both flat in dest
    assert (dest / "fav.jpg").exists()


def test_export_xmp_can_be_disabled(tmp_store, tmp_path):
    dest = tmp_path / "out"
    res = export_mod.export_to_folder(tmp_store, _seed(tmp_store, tmp_path / "src"), dest, write_xmp=False)
    assert res["xmp"] == 0
    assert not any(p.suffix == ".xmp" for p in dest.iterdir())


def test_export_zip_includes_xmp_sidecars(tmp_store, tmp_path):
    """The zip carries each original followed by its sidecar, timestamped to match the photo."""
    src = tmp_path / "src"
    sid = _seed(tmp_store, src)
    capture = datetime.datetime(2023, 8, 20, 18, 9, 12).timestamp()
    pid = next(p["id"] for p in tmp_store.list_photos(sid) if p["filename"] == "fav.jpg")
    tmp_store._conn.execute("UPDATE photos SET ctime=? WHERE id=?", (capture, pid))
    tmp_store._conn.commit()

    zpath = tmp_path / "picks.zip"
    res = export_mod.export_to_zip(tmp_store, sid, zpath)
    assert res["xmp"] == 2
    with zipfile.ZipFile(zpath) as zf:
        assert set(zf.namelist()) == {"fav.jpg", "fav.xmp", "maybe.jpg", "maybe.xmp"}
        assert _rating_label(zf.read("fav.xmp").decode()) == (5, "Green")
        # sidecar shares the photo's capture date so the pair sorts together by date
        assert zf.getinfo("fav.xmp").date_time[:3] == (2023, 8, 20)


# --- gallery export (favorites in Feed order, slot-numbered) ---

def _seed_feed(store, src_dir, favs):
    """A session with `favs` = [(name, overall)] each marked favorite, plus one maybe and one trash
    that must NOT appear in the gallery export. No embeddings → plan_feed orders by descending quality,
    so the feed order is deterministic for assertions."""
    sid = store.create_session(str(src_dir))
    for name, overall in favs:
        p = write_jpeg(src_dir / name)
        pid = store.add_photo(sid, name, str(p), is_raw=False)
        store.save_analysis(pid, emb=None, meta={}, axes={}, cats={}, overall=overall,
                            reasons=[], group_idx=0, in_group_order=0, suggested=False)
        store.add_decision(sid, pid, "favorite")
    for name, action in (("perhaps.jpg", "maybe"), ("nope.jpg", "delete")):
        p = write_jpeg(src_dir / name)
        pid = store.add_photo(sid, name, str(p), is_raw=False)
        store.save_analysis(pid, emb=None, meta={}, axes={}, cats={}, overall=0.5,
                            reasons=[], group_idx=0, in_group_order=0, suggested=False)
        store.add_decision(sid, pid, action)
    store.set_total(sid, len(favs) + 2)
    return sid


def test_export_gallery_orders_favorites_and_numbers_slots(tmp_store, tmp_path):
    src = tmp_path / "src"
    sid = _seed_feed(tmp_store, src, [("a.jpg", 0.5), ("b.jpg", 0.9), ("c.jpg", 0.7)])
    zpath = tmp_path / "gallery.zip"
    res = export_mod.export_feed_to_zip(tmp_store, sid, zpath)
    assert res["exported"] == 3 and res["missing"] == 0
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    # favorites only (no maybe/trash), slot-prefixed, in feed order (b=0.9, c=0.7, a=0.5)
    assert names == ["01_b.jpg", "02_c.jpg", "03_a.jpg"]


def test_export_gallery_order_matches_feed_view(tmp_store, tmp_path):
    """The downloaded gallery must match the on-screen Feed exactly — same order, same slot numbers."""
    from desktop_core import views
    sid = _seed_feed(tmp_store, tmp_path / "src", [("a.jpg", 0.5), ("b.jpg", 0.9), ("c.jpg", 0.7)])
    feed = views.feed_response(tmp_store, sid)["photos"]
    expected = [f"{p['slot']:02d}_{p['filename']}" for p in feed]
    zpath = tmp_path / "g.zip"
    export_mod.export_feed_to_zip(tmp_store, sid, zpath)
    with zipfile.ZipFile(zpath) as zf:
        assert zf.namelist() == expected


def test_export_gallery_excludes_maybe_and_trash(tmp_store, tmp_path):
    sid = _seed_feed(tmp_store, tmp_path / "src", [("a.jpg", 0.8)])
    zpath = tmp_path / "g.zip"
    export_mod.export_feed_to_zip(tmp_store, sid, zpath)
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    assert names == ["01_a.jpg"]                                  # the single favorite only
    assert not any("perhaps" in n or "nope" in n for n in names)  # maybe/trash absent


def test_export_gallery_no_favorites_raises(tmp_store, tmp_path):
    src = tmp_path / "src"
    sid = tmp_store.create_session(str(src))
    p = write_jpeg(src / "x.jpg")
    pid = tmp_store.add_photo(sid, "x.jpg", str(p), is_raw=False)
    tmp_store.save_analysis(pid, emb=None, meta={}, axes={}, cats={}, overall=0.5,
                            reasons=[], group_idx=0, in_group_order=0, suggested=False)
    tmp_store.add_decision(sid, pid, "maybe")  # a maybe is not a favorite → no feed to export
    with pytest.raises(ValueError):
        export_mod.export_feed_to_zip(tmp_store, sid, tmp_path / "g.zip")


def test_export_gallery_counts_missing_originals(tmp_store, tmp_path):
    src = tmp_path / "src"
    sid = _seed_feed(tmp_store, src, [("a.jpg", 0.9), ("b.jpg", 0.5)])
    (src / "a.jpg").unlink()  # a favorite's original vanished from disk
    res = export_mod.export_feed_to_zip(tmp_store, sid, tmp_path / "g.zip")
    assert res["exported"] == 1 and res["missing"] == 1


def test_export_gallery_has_no_xmp_sidecars(tmp_store, tmp_path):
    # the gallery export is for posting in order, not editing — no .xmp sidecars
    sid = _seed_feed(tmp_store, tmp_path / "src", [("a.jpg", 0.9), ("b.jpg", 0.5)])
    zpath = tmp_path / "g.zip"
    export_mod.export_feed_to_zip(tmp_store, sid, zpath)
    with zipfile.ZipFile(zpath) as zf:
        assert not any(n.endswith(".xmp") for n in zf.namelist())


def test_export_xmp_sidecar_collision_does_not_clobber(tmp_store, tmp_path):
    """A raw+jpeg pair sharing a basename maps to the same .xmp name; both must survive."""
    src = tmp_path / "src"
    sid = tmp_store.create_session(str(src))
    for name, is_raw in (("DSC1.NEF", True), ("DSC1.JPG", False)):
        p = write_jpeg(src / name)  # bytes don't matter here, only the path/extension
        pid = tmp_store.add_photo(sid, name, str(p), is_raw=is_raw)
        tmp_store.save_analysis(pid, emb=None, meta={}, axes={}, cats={}, overall=0.7,
                                reasons=[], group_idx=0, in_group_order=0, suggested=False)
        tmp_store.add_decision(sid, pid, "favorite")
    dest = tmp_path / "out"
    res = export_mod.export_to_folder(tmp_store, sid, dest)
    assert res["exported"] == 2 and res["xmp"] == 2
    xmps = sorted(p.name for p in dest.iterdir() if p.suffix == ".xmp")
    assert xmps == ["DSC1.xmp", "DSC1_1.xmp"]  # second sidecar disambiguated, not overwritten
