"""Local SQLite store for the desktop culler.

Replaces the hosted app's Postgres+pgvector. Same data model (sessions / photos / analyses /
groups / append-only decisions), but: IDs are TEXT (uuid hex), JSON columns are TEXT, the CLIP
embedding is a float32 BLOB, and photos reference **local file paths** instead of CDN URLs.

Current photo state is derived from the append-only `decisions` log (latest row per photo wins),
exactly like the hosted `app/state.py`.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL DEFAULT 'local',
    source_path  TEXT,
    title        TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    n_total      INTEGER NOT NULL DEFAULT 0,
    n_done       INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   REAL NOT NULL,
    processed_at REAL
);
CREATE TABLE IF NOT EXISTS photos (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    original_path TEXT NOT NULL,          -- original file on disk (never modified)
    preview_path TEXT,                   -- cached full-size jpeg for the lightbox
    thumb_path   TEXT,                   -- cached small jpeg for the grid
    is_raw       INTEGER NOT NULL DEFAULT 0,
    camera       TEXT,
    ctime        REAL
);
CREATE INDEX IF NOT EXISTS ix_photos_session ON photos(session_id);
CREATE TABLE IF NOT EXISTS analyses (
    photo_id       TEXT PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    emb            BLOB,                 -- float32 CLIP vector (512,)
    meta           TEXT,                 -- json
    axes           TEXT,                 -- json
    cats           TEXT,                 -- json
    overall        REAL,
    reasons        TEXT,                 -- json list
    group_idx      INTEGER,
    in_group_order INTEGER,
    suggested      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx        INTEGER NOT NULL,
    label      TEXT,
    when_ts    REAL,
    avg_score  REAL NOT NULL DEFAULT 0.0,
    close_call INTEGER NOT NULL DEFAULT 0   -- top-2 picks within a small margin: human should decide
);
CREATE INDEX IF NOT EXISTS ix_groups_session ON groups(session_id);
CREATE TABLE IF NOT EXISTS decisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    photo_id   TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    action     TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decisions_session ON decisions(session_id);
"""

ACTIONS = {"favorite", "maybe", "delete", "undo"}
_STATES = ("none", "favorite", "maybe", "delete")

# Additive schema migrations. `CREATE TABLE IF NOT EXISTS` (in _SCHEMA) covers fresh DBs and brand-new
# TABLES, but it will NOT add a new COLUMN to a table that already exists — which used to force a
# destructive `rm -rf ~/.photo-cherrypick-desktop` on every schema change, wiping the user's cull
# decisions. `_migrate()` closes that: on boot it adds any column the current code expects that an
# older DB is missing, so user data survives an app upgrade. RULE: when you add a column to _SCHEMA,
# add the matching ALTER here (NOT NULL columns need a DEFAULT so the ALTER works on existing rows).
_SCHEMA_VERSION = 1
_COLUMN_MIGRATIONS = [
    ("photos", "original_path", "ALTER TABLE photos ADD COLUMN original_path TEXT NOT NULL DEFAULT ''"),
    ("photos", "preview_path", "ALTER TABLE photos ADD COLUMN preview_path TEXT"),
    ("photos", "thumb_path", "ALTER TABLE photos ADD COLUMN thumb_path TEXT"),
    ("photos", "is_raw", "ALTER TABLE photos ADD COLUMN is_raw INTEGER NOT NULL DEFAULT 0"),
    ("photos", "camera", "ALTER TABLE photos ADD COLUMN camera TEXT"),
    ("photos", "ctime", "ALTER TABLE photos ADD COLUMN ctime REAL"),
    ("groups", "close_call", "ALTER TABLE groups ADD COLUMN close_call INTEGER NOT NULL DEFAULT 0"),
    ("analyses", "group_idx", "ALTER TABLE analyses ADD COLUMN group_idx INTEGER"),
    ("analyses", "in_group_order", "ALTER TABLE analyses ADD COLUMN in_group_order INTEGER"),
    ("analyses", "suggested", "ALTER TABLE analyses ADD COLUMN suggested INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any expected-but-missing columns (idempotent), so an older DB self-heals on boot."""
    seen: dict[str, set] = {}

    def columns(table: str) -> set:
        if table not in seen:
            seen[table] = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        return seen[table]

    for table, col, ddl in _COLUMN_MIGRATIONS:
        if col not in columns(table):
            conn.execute(ddl)
            columns(table).add(col)
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _jsonable(obj: Any) -> Any:
    """Coerce numpy scalars/arrays to native Python so json.dumps works (mirrors the hosted app)."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _new_id() -> str:
    return uuid.uuid4().hex


class CullStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        # Per-thread connections: the FastAPI request threads and the background analysis worker
        # each get their own sqlite connection. A single shared connection is NOT safe across
        # threads (check_same_thread=False only silences the assertion; it does not serialise
        # transactions). WAL + busy_timeout let readers run lock-free and serialise the rare
        # writer-vs-writer case (worker vs. a decision/rename/delete) without data loss.
        self._local = threading.local()
        boot = self._connect()
        boot.executescript(_SCHEMA)   # fresh DBs + any new tables
        _migrate(boot)                # self-heal older DBs: add columns they're missing (no data loss)
        boot.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        self._local.conn = conn
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        return conn if conn is not None else self._connect()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # --- sessions ---
    def create_session(self, source_path: str, title: str | None = None) -> str:
        sid = _new_id()
        self._conn.execute(
            "INSERT INTO sessions(id, source, source_path, title, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (sid, "local", source_path, title or Path(source_path).name, "pending", time.time()),
        )
        self._conn.commit()
        return sid

    def set_status(self, sid: str, status: str, error: str | None = None) -> None:
        processed = time.time() if status == "ready" else None
        self._conn.execute(
            "UPDATE sessions SET status=?, error=?, processed_at=COALESCE(?, processed_at) WHERE id=?",
            (status, error, processed, sid),
        )
        self._conn.commit()

    def set_total(self, sid: str, n_total: int) -> None:
        self._conn.execute("UPDATE sessions SET n_total=?, n_done=0 WHERE id=?", (n_total, sid))
        self._conn.commit()

    def set_progress(self, sid: str, n_done: int) -> None:
        self._conn.execute("UPDATE sessions SET n_done=? WHERE id=?", (n_done, sid))
        self._conn.commit()

    def rename(self, sid: str, title: str) -> bool:
        cur = self._conn.execute("UPDATE sessions SET title=? WHERE id=?", (title.strip(), sid))
        self._conn.commit()
        return cur.rowcount > 0

    def delete_session(self, sid: str) -> bool:
        cur = self._conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_session(self, sid: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    # --- photos ---
    def add_photo(self, sid: str, filename: str, path: str, is_raw: bool) -> str:
        pid = _new_id()
        self._conn.execute(
            "INSERT INTO photos(id, session_id, filename, original_path, is_raw) VALUES (?,?,?,?,?)",
            (pid, sid, filename, path, 1 if is_raw else 0),
        )
        self._conn.commit()
        return pid

    def set_photo_cache(self, pid: str, preview_path: str, thumb_path: str) -> None:
        self._conn.execute(
            "UPDATE photos SET preview_path=?, thumb_path=? WHERE id=?", (preview_path, thumb_path, pid)
        )
        self._conn.commit()

    def set_photo_meta(self, pid: str, camera: str | None, ctime: float | None) -> None:
        self._conn.execute("UPDATE photos SET camera=?, ctime=? WHERE id=?", (camera, ctime, pid))
        self._conn.commit()

    def list_photos(self, sid: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM photos WHERE session_id=?", (sid,)).fetchall()
        return [dict(r) for r in rows]

    def get_photo(self, pid: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    # --- analyses & groups ---
    def save_analysis(
        self, pid: str, *, emb: np.ndarray | None, meta: dict, axes: dict, cats: dict,
        overall: float, reasons: list[str], group_idx: int, in_group_order: int, suggested: bool,
    ) -> None:
        blob = np.asarray(emb, dtype=np.float32).tobytes() if emb is not None else None
        self._conn.execute(
            "INSERT OR REPLACE INTO analyses(photo_id, emb, meta, axes, cats, overall, reasons, "
            "group_idx, in_group_order, suggested) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pid, blob,
                json.dumps(_jsonable(meta)), json.dumps(_jsonable(axes)), json.dumps(_jsonable(cats)),
                float(overall), json.dumps(list(reasons)),
                int(group_idx), int(in_group_order), 1 if suggested else 0,
            ),
        )
        self._conn.commit()

    def save_group(self, sid: str, idx: int, label: str, when_ts: float | None,
                   avg_score: float, close_call: bool = False) -> None:
        self._conn.execute(
            "INSERT INTO groups(session_id, idx, label, when_ts, avg_score, close_call) "
            "VALUES (?,?,?,?,?,?)",
            (sid, int(idx), label, when_ts, float(avg_score), 1 if close_call else 0),
        )
        self._conn.commit()

    def get_groups(self, sid: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT idx, label, when_ts, avg_score, close_call FROM groups WHERE session_id=? ORDER BY idx",
            (sid,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_embeddings(self, sid: str) -> dict[str, np.ndarray]:
        """photo_id -> L2-normalized CLIP vector, for on-demand scene clustering.

        Kept separate from get_analyses() (which drops the blob) so the common read path stays
        lightweight — embeddings are only loaded for the scene-grouping view.
        """
        rows = self._conn.execute(
            "SELECT a.photo_id, a.emb FROM analyses a JOIN photos p ON a.photo_id=p.id "
            "WHERE p.session_id=? AND a.emb IS NOT NULL",
            (sid,),
        ).fetchall()
        return {r["photo_id"]: np.frombuffer(r["emb"], dtype=np.float32) for r in rows}

    def get_analyses(self, sid: str) -> dict[str, dict]:
        rows = self._conn.execute(
            "SELECT a.* FROM analyses a JOIN photos p ON a.photo_id=p.id WHERE p.session_id=?", (sid,)
        ).fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
            d["axes"] = json.loads(d["axes"]) if d["axes"] else {}
            d["cats"] = json.loads(d["cats"]) if d["cats"] else {}
            d["reasons"] = json.loads(d["reasons"]) if d["reasons"] else []
            d.pop("emb", None)
            out[d["photo_id"]] = d
        return out

    # --- decisions / state (append-only; latest row per photo wins) ---
    def add_decision(self, sid: str, pid: str, action: str) -> str:
        if action not in ACTIONS:
            raise ValueError(f"bad action: {action}")
        self._conn.execute(
            "INSERT INTO decisions(session_id, photo_id, action, created_at) VALUES (?,?,?,?)",
            (sid, pid, action, time.time()),
        )
        self._conn.commit()
        return "none" if action == "undo" else action

    def accept_suggestions(self, sid: str) -> int:
        """Favorite every still-undecided suggested pick (the best-of-burst frames). Existing
        decisions are left untouched. Returns how many picks were newly favorited."""
        states = self.current_states(sid)
        rows = self._conn.execute(
            "SELECT a.photo_id FROM analyses a JOIN photos p ON a.photo_id=p.id "
            "WHERE p.session_id=? AND a.suggested=1",
            (sid,),
        ).fetchall()
        accepted = 0
        for r in rows:
            pid = r["photo_id"]
            if states.get(pid, "none") == "none":   # don't clobber a manual decision
                self.add_decision(sid, pid, "favorite")
                accepted += 1
        return accepted

    def current_states(self, sid: str) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT photo_id, action FROM decisions WHERE id IN "
            "(SELECT MAX(id) FROM decisions WHERE session_id=? GROUP BY photo_id)",
            (sid,),
        ).fetchall()
        return {r["photo_id"]: ("none" if r["action"] == "undo" else r["action"]) for r in rows}

    def counts(self, sid: str, n_total: int | None = None) -> dict[str, int]:
        if n_total is None:
            row = self._conn.execute("SELECT n_total FROM sessions WHERE id=?", (sid,)).fetchone()
            n_total = row["n_total"] if row else 0
        states = self.current_states(sid)
        out = {s: 0 for s in _STATES}
        for st in states.values():
            out[st] = out.get(st, 0) + 1
        out["none"] = max(0, n_total - (out["favorite"] + out["maybe"] + out["delete"]))
        return out
