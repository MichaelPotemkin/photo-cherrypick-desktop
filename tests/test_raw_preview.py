import io
import sys
import types
from pathlib import Path

from PIL import Image

from desktop_core import raw_preview as rp
from tests.conftest import write_jpeg, write_png


def test_extension_classification():
    assert rp.is_raw(Path("a.CR3")) and rp.is_raw(Path("b.nef")) and rp.is_raw(Path("c.arw"))
    assert not rp.is_raw(Path("d.jpg"))


class _FakeExif(dict):
    """Minimal stand-in for a PIL Exif object: dict-like base IFD + a separate ExifIFD."""
    def get_ifd(self, _tag):
        return getattr(self, "sub", {})


def test_capture_time_prefers_original_then_falls_back_to_base_datetime():
    import datetime

    from pipeline.embed import capture_time

    want = datetime.datetime(2023, 8, 20, 18, 9, 12).timestamp()

    # RAW embedded preview: only the base-IFD DateTime (0x0132) is present, no DateTimeOriginal
    base_only = _FakeExif({0x0132: "2023:08:20 18:09:12"})
    base_only.sub = {}
    assert capture_time(base_only) == want

    # DateTimeOriginal (in the ExifIFD) takes precedence over the base DateTime
    with_original = _FakeExif({0x0132: "2000:01:01 00:00:00"})
    with_original.sub = {0x9003: "2023:08:20 18:09:12"}
    assert capture_time(with_original) == want

    # nothing usable -> None
    empty = _FakeExif({})
    empty.sub = {}
    assert capture_time(empty) is None
    assert rp.is_image(Path("d.jpg")) and rp.is_image(Path("e.PNG")) and rp.is_image(Path("f.dng"))
    assert not rp.is_image(Path("notes.txt"))


def test_load_rgb_jpeg(tmp_path):
    p = write_jpeg(tmp_path / "x.jpg", size=(100, 60))
    img = rp.load_rgb(p)
    assert img is not None and img.mode == "RGB" and img.size == (100, 60)


def test_load_rgb_png(tmp_path):
    img = rp.load_rgb(write_png(tmp_path / "x.png"))
    assert img is not None and img.mode == "RGB"


def test_load_rgb_unrenderable_returns_none(tmp_path):
    # a file with a RAW extension that isn't actually a RAW must degrade gracefully, not crash
    bogus = tmp_path / "fake.nef"
    bogus.write_bytes(b"not a real raw file")
    assert rp.load_rgb(bogus) is None


def test_raw_embedded_preview_applies_orientation(tmp_path, monkeypatch):
    """Embedded RAW preview (a JPEG with Orientation=6) must be EXIF-transposed, like the
    non-RAW path — otherwise portrait RAWs analyze/display sideways."""
    base = Image.new("RGB", (8, 4), (123, 50, 200))   # 8x4 landscape pixels
    exif = base.getexif()
    exif[274] = 6                                       # Orientation: rotate 90° -> 4x8 upright
    buf = io.BytesIO()
    base.save(buf, "JPEG", exif=exif)
    jpeg_bytes = buf.getvalue()

    class ThumbFormat:
        JPEG = 1
        BITMAP = 2

    class _Thumb:
        format = ThumbFormat.JPEG
        data = jpeg_bytes

    class _Raw:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_thumb(self):
            return _Thumb()

    fake_rawpy = types.ModuleType("rawpy")
    fake_rawpy.ThumbFormat = ThumbFormat
    fake_rawpy.imread = lambda _p: _Raw()
    monkeypatch.setitem(sys.modules, "rawpy", fake_rawpy)

    p = tmp_path / "portrait.nef"
    p.write_bytes(b"raw-bytes")
    img = rp.load_rgb(p)
    assert img is not None
    assert img.size == (4, 8)  # transposed from 8x4 -> 4x8 (orientation honoured)


def test_make_thumbnail_bounds(tmp_path):
    img = rp.load_rgb(write_jpeg(tmp_path / "x.jpg", size=(2000, 1000)))
    thumb = rp.make_thumbnail(img, max_side=256)
    assert max(thumb.size) <= 256
    assert img.size == (2000, 1000)  # original copy untouched
