import sqlite3
import threading

import numpy as np
import pytest

from desktop_core.store import CullStore
from tests.conftest import make_meta


def test_migrate_self_heals_old_schema(tmp_path):
    """An older DB missing columns (the bug that used to force `rm -rf`) must self-heal on open,
    preserving existing rows, with no destructive reset."""
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, source_path TEXT, title TEXT,
            status TEXT, n_total INTEGER, n_done INTEGER, error TEXT, created_at REAL, processed_at REAL);
        CREATE TABLE photos (id TEXT PRIMARY KEY, session_id TEXT, filename TEXT);  -- pre-original_path/cache
        CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, idx INTEGER,
            label TEXT, when_ts REAL, avg_score REAL);                              -- pre-close_call
        CREATE TABLE analyses (photo_id TEXT PRIMARY KEY, emb BLOB, meta TEXT, axes TEXT, cats TEXT,
            overall REAL, reasons TEXT, group_idx INTEGER);                         -- pre-in_group_order/suggested
        CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, photo_id TEXT,
            action TEXT, created_at REAL);
        """
    )
    con.execute("INSERT INTO sessions(id, title, created_at) VALUES ('s1', 'Old', 1.0)")
    con.commit()
    con.close()

    store = CullStore(db)   # opening migrates it
    photo_cols = {r[1] for r in store._conn.execute("PRAGMA table_info(photos)")}
    assert {"original_path", "preview_path", "thumb_path", "is_raw", "camera", "ctime"} <= photo_cols
    assert "close_call" in {r[1] for r in store._conn.execute("PRAGMA table_info(groups)")}
    assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert store.get_session("s1")["title"] == "Old"   # existing data preserved

    # the migrated DB works end-to-end against the new columns
    pid = store.add_photo("s1", "a.jpg", "/x/a.jpg", is_raw=True)
    store.save_group("s1", 0, "g", None, 0.5, close_call=True)
    assert store.get_groups("s1")[0]["close_call"] == 1
    assert store.get_photo(pid)["original_path"] == "/x/a.jpg"
    store.close()


def test_accept_suggestions_favorites_only_undecided(tmp_store):
    sid = tmp_store.create_session("/x")
    p1 = tmp_store.add_photo(sid, "a.jpg", "/x/a.jpg", False)
    p2 = tmp_store.add_photo(sid, "b.jpg", "/x/b.jpg", False)
    p3 = tmp_store.add_photo(sid, "c.jpg", "/x/c.jpg", False)
    common = dict(emb=None, meta={}, axes={}, cats={}, reasons=[], in_group_order=0)
    tmp_store.save_analysis(p1, overall=0.8, group_idx=0, suggested=True, **common)
    tmp_store.save_analysis(p2, overall=0.7, group_idx=1, suggested=True, **common)
    tmp_store.save_analysis(p3, overall=0.6, group_idx=2, suggested=False, **common)
    tmp_store.add_decision(sid, p2, "delete")   # manual decision on a suggested pick

    assert tmp_store.accept_suggestions(sid) == 1   # only p1 (suggested AND undecided)
    states = tmp_store.current_states(sid)
    assert states[p1] == "favorite"
    assert states[p2] == "delete"                   # manual decision NOT clobbered
    assert states.get(p3, "none") == "none"         # non-suggested untouched
    assert tmp_store.accept_suggestions(sid) == 0   # idempotent — nothing left undecided


def test_accept_suggestions_is_atomic_on_failure(tmp_store, monkeypatch):
    """If a write fails part-way through accept_suggestions, the whole batch rolls back — not even
    the favorites that already succeeded are committed (regression guard for the transaction fix)."""
    sid = tmp_store.create_session("/x")
    common = dict(emb=None, meta={}, axes={}, cats={}, reasons=[], in_group_order=0)
    for i in range(3):
        p = tmp_store.add_photo(sid, f"{i}.jpg", f"/x/{i}.jpg", False)
        tmp_store.save_analysis(p, overall=0.8, group_idx=i, suggested=True, **common)

    # blow up on the SECOND insert, after the first has already executed inside the transaction
    real = tmp_store._insert_decision
    calls = {"n": 0}

    def boom(s, pid, action):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("boom")
        return real(s, pid, action)

    monkeypatch.setattr(tmp_store, "_insert_decision", boom)

    with pytest.raises(sqlite3.OperationalError):
        tmp_store.accept_suggestions(sid)

    # the `with self._conn:` block rolled the whole batch back — no partial favorites landed
    assert tmp_store.current_states(sid) == {}
    assert tmp_store.count_pending_suggestions(sid) == 3


def test_count_pending_suggestions(tmp_store):
    sid = tmp_store.create_session("/x")
    common = dict(emb=None, meta={}, axes={}, cats={}, reasons=[], in_group_order=0)
    p1 = tmp_store.add_photo(sid, "a.jpg", "/x/a.jpg", False)
    p2 = tmp_store.add_photo(sid, "b.jpg", "/x/b.jpg", False)
    p3 = tmp_store.add_photo(sid, "c.jpg", "/x/c.jpg", False)
    tmp_store.save_analysis(p1, overall=0.8, group_idx=0, suggested=True, **common)
    tmp_store.save_analysis(p2, overall=0.7, group_idx=1, suggested=True, **common)
    tmp_store.save_analysis(p3, overall=0.6, group_idx=2, suggested=False, **common)

    assert tmp_store.count_pending_suggestions(sid) == 2    # both suggested + undecided
    tmp_store.add_decision(sid, p1, "favorite")
    assert tmp_store.count_pending_suggestions(sid) == 1    # p1 now decided
    tmp_store.add_decision(sid, p2, "delete")
    assert tmp_store.count_pending_suggestions(sid) == 0    # a non-favorite decision still counts as decided


def test_migrate_is_idempotent_on_current_schema(tmp_path):
    """Opening a current-schema DB twice must not error (all columns already present)."""
    db = tmp_path / "cur.db"
    CullStore(db).close()
    store = CullStore(db)   # second open: migrations find nothing to add
    assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    store.close()


def test_migrate_v2_backfills_single_shot_suggested(tmp_path):
    """A pre-v2 DB left single-shot groups un-suggested, so 'Accept picks' skipped them. Opening must
    backfill the sole frame of each single-member group, without touching multi-shot groups."""
    db = tmp_path / "v1.db"
    store = CullStore(db)
    sid = store.create_session("/x")
    common = dict(emb=None, meta={}, axes={}, cats={}, reasons=[], in_group_order=0)
    solo = store.add_photo(sid, "solo.jpg", "/x/solo.jpg", False)
    store.save_analysis(solo, overall=0.5, group_idx=0, suggested=False, **common)   # single-shot group
    # a 2-frame burst (group 1): one suggested, one not — must be left alone
    b0 = store.add_photo(sid, "b0.jpg", "/x/b0.jpg", False)
    b1 = store.add_photo(sid, "b1.jpg", "/x/b1.jpg", False)
    store.save_analysis(b0, overall=0.8, group_idx=1, suggested=True, **{**common, "in_group_order": 0})
    store.save_analysis(b1, overall=0.7, group_idx=1, suggested=False, **{**common, "in_group_order": 1})
    store._conn.execute("PRAGMA user_version = 1")   # simulate a pre-v2 DB
    store._conn.commit()
    store.close()

    store2 = CullStore(db)   # opening runs the v2 data migration
    sug = dict(store2._conn.execute("SELECT photo_id, suggested FROM analyses"))
    assert sug[solo] == 1                              # single-shot backfilled
    assert sug[b0] == 1 and sug[b1] == 0               # burst untouched
    assert store2.count_pending_suggestions(sid) == 2  # solo + b0, now both counted by Accept picks
    store2.close()


def test_session_crud_and_list(tmp_store):
    sid = tmp_store.create_session("/photos/shoot", title="Shoot")
    assert tmp_store.get_session(sid)["status"] == "pending"
    assert tmp_store.rename(sid, "  Renamed  ") is True
    assert tmp_store.get_session(sid)["title"] == "Renamed"  # trimmed
    assert [s["id"] for s in tmp_store.list_sessions()] == [sid]
    assert tmp_store.delete_session(sid) is True
    assert tmp_store.get_session(sid) is None
    assert tmp_store.rename("nope", "x") is False
    assert tmp_store.delete_session("nope") is False


def test_decisions_latest_wins_and_counts(tmp_store):
    sid = tmp_store.create_session("/p")
    p1 = tmp_store.add_photo(sid, "a.jpg", "/p/a.jpg", is_raw=False)
    p2 = tmp_store.add_photo(sid, "b.cr3", "/p/b.cr3", is_raw=True)
    p3 = tmp_store.add_photo(sid, "c.jpg", "/p/c.jpg", is_raw=False)
    tmp_store.set_total(sid, 3)

    tmp_store.add_decision(sid, p1, "favorite")
    tmp_store.add_decision(sid, p1, "maybe")     # supersedes favorite
    tmp_store.add_decision(sid, p2, "delete")
    tmp_store.add_decision(sid, p3, "favorite")
    tmp_store.add_decision(sid, p3, "undo")      # back to none

    states = tmp_store.current_states(sid)
    assert states[p1] == "maybe" and states[p2] == "delete" and states[p3] == "none"
    counts = tmp_store.counts(sid)
    assert counts == {"none": 1, "favorite": 0, "maybe": 1, "delete": 1}


def test_save_and_read_analysis_roundtrip(tmp_store):
    sid = tmp_store.create_session("/p")
    pid = tmp_store.add_photo(sid, "a.jpg", "/p/a.jpg", is_raw=False)
    m = make_meta(name="a.jpg")
    emb = m["emb"]
    tmp_store.save_analysis(
        pid, emb=emb, meta={"is_bw": True, "sharp": 120.0}, axes={"exposure": 0.9},
        cats={"focus": 0.8}, overall=0.77, reasons=["sharp eyes"], group_idx=0,
        in_group_order=0, suggested=True,
    )
    got = tmp_store.get_analyses(sid)[pid]
    assert got["overall"] == 0.77 and got["suggested"] == 1
    assert got["meta"]["is_bw"] is True and got["reasons"] == ["sharp eyes"]
    assert got["axes"]["exposure"] == 0.9


def test_concurrent_writes_and_reads_no_loss(tmp_path):
    """Worker-thread writes + request-thread writes + readers must not lose rows or error.

    Regression for the shared-connection bug: each thread gets its own connection (WAL +
    busy_timeout), so concurrent committers serialise without 'API misuse' / lost decisions.
    """
    store = CullStore(tmp_path / "concurrent.db")
    sid = store.create_session("/p")
    pids = [store.add_photo(sid, f"{i}.jpg", f"/p/{i}.jpg", is_raw=False) for i in range(20)]
    store.set_total(sid, 20)
    errors: list[Exception] = []

    def writer(start: int):
        try:
            for k in range(25):
                store.add_decision(sid, pids[(start + k) % 20], "favorite")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            for _ in range(100):
                store.counts(sid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    threads += [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    n = store._conn.execute(
        "SELECT COUNT(*) AS c FROM decisions WHERE session_id=?", (sid,)
    ).fetchone()["c"]
    assert n == 8 * 25  # every write landed, none dropped
    store.close()


def test_delete_cascades(tmp_store):
    sid = tmp_store.create_session("/p")
    pid = tmp_store.add_photo(sid, "a.jpg", "/p/a.jpg", is_raw=False)
    tmp_store.save_analysis(pid, emb=np.zeros(512, np.float32), meta={}, axes={}, cats={},
                            overall=0.5, reasons=[], group_idx=0, in_group_order=0, suggested=False)
    tmp_store.add_decision(sid, pid, "favorite")
    tmp_store.save_group(sid, 0, "single shot", None, 0.5)

    tmp_store.delete_session(sid)
    # foreign_keys=ON => children gone
    assert tmp_store.list_photos(sid) == []
    assert tmp_store.get_analyses(sid) == {}
    assert tmp_store.get_groups(sid) == []
    assert tmp_store.current_states(sid) == {}
