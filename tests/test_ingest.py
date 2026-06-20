from desktop_core.ingest import scan_folder
from tests.conftest import write_jpeg, write_png


def test_scan_pairs_raw_and_jpeg(tmp_path):
    write_jpeg(tmp_path / "IMG_001.JPG")
    (tmp_path / "IMG_001.CR3").write_bytes(b"raw")          # RAW sidecar of the same shot
    write_png(tmp_path / "IMG_002.png")
    (tmp_path / ".hidden.jpg").write_bytes(b"x")            # hidden -> ignored
    (tmp_path / "notes.txt").write_text("nope")            # non-image -> ignored

    items = {it.filename: it for it in scan_folder(tmp_path)}
    assert set(items) == {"IMG_001.CR3", "IMG_002.png"}    # one item per shot; RAW wins as original

    raw_item = items["IMG_001.CR3"]
    assert raw_item.is_raw is True
    assert raw_item.original_path.endswith("IMG_001.CR3")   # export the RAW
    assert raw_item.load_path.endswith("IMG_001.JPG")       # but load the JPEG sidecar (EXIF + speed)

    png_item = items["IMG_002.png"]
    assert png_item.is_raw is False
    assert png_item.original_path == png_item.load_path


def test_scan_recursive_and_ordering(tmp_path):
    write_jpeg(tmp_path / "b.jpg")
    write_jpeg(tmp_path / "sub" / "a.jpg")
    items = scan_folder(tmp_path, recursive=True)
    assert [it.filename for it in items] == ["a.jpg", "b.jpg"]  # sorted, recursive
    assert len(scan_folder(tmp_path, recursive=False)) == 1     # only top-level b.jpg
