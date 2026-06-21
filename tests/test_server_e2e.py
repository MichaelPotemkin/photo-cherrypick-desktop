"""Hermetic end-to-end through the FastAPI app (TestClient), analyze monkeypatched.

Exercises: create-from-folder -> ready -> groups -> decision -> counts -> image serving ->
export (zip + csv) -> rename -> delete. Runs synchronously (CULL_SYNC) with faked models.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from desktop_core import pipeline_runner
from tests.conftest import make_meta, write_jpeg

os.environ["CULL_SYNC"] = "1"  # process inline so the POST returns when analysis is done


@pytest.fixture
def client(tmp_path, monkeypatch):
    # fake the heavy bits; keep real grouping/scoring/persistence/views
    monkeypatch.setattr(pipeline_runner, "warmup", lambda: None)
    monkeypatch.setattr(pipeline_runner, "capture_time", lambda exif: None)
    monkeypatch.setattr(pipeline_runner, "camera_id", lambda exif, name: "model:Cam")
    embs = {w: make_meta(name=str(w), seed=w)["emb"] for w in (100, 101, 102)}
    script = {
        100: make_meta(name="100", emb=embs[100], ctime=1000.0),
        101: make_meta(name="101", emb=embs[101], ctime=4000.0),
        102: make_meta(name="102", emb=embs[102], ctime=8000.0),
    }
    monkeypatch.setattr(pipeline_runner, "analyze", lambda img, ctime=None: dict(script[img.size[0]]))

    from server.app import create_app
    app = create_app(data_dir=tmp_path / "data")
    return TestClient(app)


@pytest.fixture
def src_folder(tmp_path):
    d = tmp_path / "shoot"
    for w in (100, 101, 102):
        write_jpeg(d / f"{w}.jpg", size=(w, 60))
    return str(d)


def test_create_rejects_non_folder(client):
    r = client.post("/api/sessions", json={"path": "/no/such/dir"})
    assert r.status_code == 400


def test_full_flow(client, src_folder):
    # create (sync) -> ready
    r = client.post("/api/sessions", json={"path": src_folder})
    assert r.status_code == 200
    sid = r.json()["id"]

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["status"] == "ready" and detail["n_total"] == 3
    assert detail["source_url"] == src_folder  # local path surfaced in the URL field

    groups = client.get(f"/api/sessions/{sid}/groups").json()["groups"]
    photos = [p for g in groups for p in g["photos"]]
    assert len(photos) == 3
    pid = photos[0]["id"]
    assert photos[0]["preview_url"] == f"/api/img/{pid}/preview"

    # image serving from disk — content-addressed, so it carries a cache header (issue #87)
    thumb = client.get(f"/api/img/{pid}/thumb")
    assert thumb.status_code == 200
    assert "max-age" in thumb.headers.get("cache-control", "")
    assert client.get(f"/api/img/{pid}/preview").status_code == 200
    assert client.get(f"/api/img/{pid}/original").status_code == 200

    # decision -> counts
    assert client.post(f"/api/photos/{pid}/decision", json={"action": "favorite"}).json()["state"] == "favorite"
    assert client.get(f"/api/sessions/{sid}").json()["counts"]["favorite"] == 1
    # bad action / unknown photo
    assert client.post(f"/api/photos/{pid}/decision", json={"action": "nope"}).status_code == 400
    assert client.post("/api/photos/deadbeef/decision", json={"action": "favorite"}).status_code == 404

    # export (zip only; the csv/scores report was removed)
    assert client.get(f"/api/sessions/{sid}/export?format=csv").status_code == 400
    z = client.get(f"/api/sessions/{sid}/export?format=zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"

    # rename + delete
    assert client.patch(f"/api/sessions/{sid}", json={"title": "My Shoot"}).json()["title"] == "My Shoot"
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_export_nothing_is_400(client, src_folder):
    sid = client.post("/api/sessions", json={"path": src_folder}).json()["id"]
    assert client.get(f"/api/sessions/{sid}/export?format=zip").status_code == 400  # no picks


def test_spa_deep_link_falls_back_and_api_404_stays_json(client):
    import server.app as appmod
    spa = Path(appmod.__file__).resolve().parent.parent / "frontend" / "dist"
    if (spa / "index.html").exists():   # only meaningful once the SPA is built
        r = client.get("/session/abc123")           # a client-side route, refreshed
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/api/definitely-not-a-route").status_code == 404   # API 404s stay JSON


def test_accept_suggestions_endpoint(client, src_folder):
    sid = client.post("/api/sessions", json={"path": src_folder}).json()["id"]
    r = client.post(f"/api/sessions/{sid}/accept-suggestions")
    assert r.status_code == 200
    body = r.json()
    assert "accepted" in body and "counts" in body
    assert client.post("/api/sessions/nope/accept-suggestions").status_code == 404


def test_feed_orders_favorites(client, src_folder):
    sid = client.post("/api/sessions", json={"path": src_folder}).json()["id"]
    assert client.get(f"/api/sessions/{sid}/feed").json()["photos"] == []   # no favorites -> empty
    assert client.get("/api/sessions/nope/feed").status_code == 404

    pics = [p for g in client.get(f"/api/sessions/{sid}/groups").json()["groups"] for p in g["photos"]][:2]
    for p in pics:
        client.post(f"/api/photos/{p['id']}/decision", json={"action": "favorite"})
    feed = client.get(f"/api/sessions/{sid}/feed").json()["photos"]
    assert {f["id"] for f in feed} == {p["id"] for p in pics}          # only favorites, all of them
    assert [f["slot"] for f in feed] == [1, 2]                          # 1-based feed order
    assert all(f["scale"] in ("close", "medium", "wide") for f in feed)


def test_scene_mode_groups_keepers_and_excludes_trash(client, src_folder):
    sid = client.post("/api/sessions", json={"path": src_folder}).json()["id"]

    # bad mode is rejected; default (burst) and scene both 200
    assert client.get(f"/api/sessions/{sid}/groups?mode=bogus").status_code == 400
    scene = client.get(f"/api/sessions/{sid}/groups?mode=scene").json()["groups"]
    photos = [p for g in scene for p in g["photos"]]
    assert len(photos) == 3                       # all keepers clustered
    assert all(isinstance(g["close_call"], bool) for g in scene)
    assert all(g["label"] in ("unique look",) or "in scene" in g["label"] for g in scene)

    # trash one photo -> the scene view drops it (second pass works on keepers only)
    trash_id = photos[0]["id"]
    client.post(f"/api/photos/{trash_id}/decision", json={"action": "delete"})
    scene2 = client.get(f"/api/sessions/{sid}/groups?mode=scene").json()["groups"]
    ids2 = {p["id"] for g in scene2 for p in g["photos"]}
    assert trash_id not in ids2 and len(ids2) == 2
    # burst mode still shows every photo, trashed included
    burst_ids = {p["id"] for g in client.get(f"/api/sessions/{sid}/groups").json()["groups"] for p in g["photos"]}
    assert trash_id in burst_ids and len(burst_ids) == 3
