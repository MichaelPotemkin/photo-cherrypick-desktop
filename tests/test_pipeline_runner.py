"""End-to-end run_session orchestration with a scripted (monkeypatched) analyze.

No torch models run: analyze is faked, but compute_refs / build_groups / axis_scores / the
suggestion-sort + blink penalty / persistence / read-model are all the real code.
"""
import numpy as np
import pytest

from desktop_core import pipeline_runner
from desktop_core.ingest import FileItem
from desktop_core.views import groups_response
from tests.conftest import make_meta, write_jpeg

# scripted measurement dicts keyed by image WIDTH (the test encodes an index into image width)
E1 = make_meta(name="_")["emb"]
E2 = np.roll(E1, 11)
E3 = np.roll(E1, 23)
SCRIPT = {
    100: make_meta(name="a", emb=E1, ctime=1000.0, eyes=2, face_sharp=200.0, eye_sharp=200.0),
    101: make_meta(name="b", emb=E1, ctime=1001.0, eyes=2, face_sharp=150.0, eye_sharp=150.0),
    102: make_meta(name="c", emb=E2, ctime=2000.0, eyes=2, face_sharp=150.0, eye_sharp=150.0),
    103: make_meta(name="d", emb=E2, ctime=2001.0, eyes=0, face_sharp=260.0, eye_sharp=260.0),  # blink, sharper
    104: make_meta(name="e", emb=E3, ctime=5000.0, eyes=2),
}


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(pipeline_runner, "warmup", lambda: None)
    monkeypatch.setattr(pipeline_runner, "capture_time", lambda exif: None)
    monkeypatch.setattr(pipeline_runner, "camera_id", lambda exif, name: "model:TestCam")

    def fake_analyze(img, ctime=None):
        return dict(SCRIPT[img.size[0]])  # copy; width is the script key

    monkeypatch.setattr(pipeline_runner, "analyze", fake_analyze)


def _items(tmp_path):
    items = []
    for w, m in SCRIPT.items():
        p = write_jpeg(tmp_path / f"{m['name']}.jpg", size=(w, 60))
        items.append(FileItem(filename=p.name, original_path=str(p), load_path=str(p), is_raw=False))
    return items


def test_full_run(patched, tmp_store, tmp_path):
    sid = tmp_store.create_session("/s")
    items = _items(tmp_path / "src")
    summary = pipeline_runner.run_session(tmp_store, sid, items, tmp_path / "cache")

    assert summary["analyzed"] == 5 and summary["unsupported"] == []
    assert tmp_store.get_session(sid)["status"] == "ready"

    data = groups_response(tmp_store, sid)
    groups = data["groups"]
    # {a,b}, {c,d}, {e}
    assert sorted(len(g["photos"]) for g in groups) == [1, 2, 2]

    # every overall in [0,1]; multi-shot groups have exactly one suggested
    for g in groups:
        for p in g["photos"]:
            assert 0.0 <= p["overall"] <= 1.0
        if len(g["photos"]) > 1:
            assert sum(p["suggested"] for p in g["photos"]) == 1

    def suggested_name(group):
        return next(p["filename"] for p in group["photos"] if p["suggested"])

    ab = next(g for g in groups if {p["filename"] for p in g["photos"]} == {"a.jpg", "b.jpg"})
    cd = next(g for g in groups if {p["filename"] for p in g["photos"]} == {"c.jpg", "d.jpg"})
    assert suggested_name(ab) == "a.jpg"          # a is sharper -> picked
    assert suggested_name(cd) == "c.jpg"          # d is sharper but a blink -> demoted; c picked


def test_cache_files_written(patched, tmp_store, tmp_path):
    sid = tmp_store.create_session("/s")
    items = _items(tmp_path / "src")
    pipeline_runner.run_session(tmp_store, sid, items, tmp_path / "cache")
    for photo in tmp_store.list_photos(sid):
        assert photo["preview_path"] and photo["thumb_path"]
        from pathlib import Path
        assert Path(photo["preview_path"]).exists() and Path(photo["thumb_path"]).exists()
