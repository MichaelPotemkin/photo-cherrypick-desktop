# Database schema migrations

The desktop app keeps the user's library in a local SQLite file
(`~/.photo-cherrypick-desktop/cull.db`, overridable via `CULL_DATA_DIR`). That file holds the
user's actual cull decisions — favorites, maybes, deletes — so a schema change must **never** force a
destructive `rm -rf` of the data dir. `desktop_core/store.py` implements an additive migration system
so an older DB self-heals on open and user data survives an app upgrade.

This doc is the recipe for adding a column / table and bumping the version without breaking it. It is
accurate to `desktop_core/store.py` as written; if you change the migration code, update this doc too.

## Where the pieces live

Everything is in `desktop_core/store.py`:

- **`_SCHEMA`** — the `CREATE TABLE IF NOT EXISTS …` script for the full, current schema. This is the
  source of truth for a *fresh* DB.
- **`_SCHEMA_VERSION`** — the integer schema version constant (currently `2`). Written into the DB's
  `PRAGMA user_version` after migrating.
- **`_COLUMN_MIGRATIONS`** — a list of `(table, column, ddl)` tuples; one `ALTER TABLE … ADD COLUMN`
  per column the current code expects.
- **`_migrate(conn)`** — runs the column migrations, then any version-keyed *data* migrations, then
  stamps `user_version = _SCHEMA_VERSION`.

## How and when migrations run

`_migrate()` runs **once per process, on store open**. In `CullStore.__init__`:

```python
boot = self._connect()
boot.executescript(_SCHEMA)   # fresh DBs + any new tables
_migrate(boot)                # self-heal older DBs: add columns they're missing (no data loss)
boot.commit()
```

So the boot sequence is:

1. `executescript(_SCHEMA)` — `CREATE TABLE IF NOT EXISTS` creates any **table** (and its indexes)
   that doesn't exist yet. This covers brand-new DBs and brand-new tables, but it does **not** add a
   new **column** to a table that already exists — that's the gap `_migrate()` fills.
2. `_migrate(boot)` — for every `(table, col, ddl)` in `_COLUMN_MIGRATIONS`, if `col` is absent from
   that table's `PRAGMA table_info`, run the `ALTER`. Then run version-gated data migrations. Then set
   `user_version`.

Column existence is read from `PRAGMA table_info(<table>)` (cached per table within the call), so the
column pass is **idempotent** — on a current-schema DB it finds nothing to add and is a no-op.

## The existing migration, as a worked example

### Column migrations (the `_COLUMN_MIGRATIONS` list)

These backfill columns that were added to `photos`, `groups`, and `analyses` after the original
schema shipped, e.g.:

```python
_COLUMN_MIGRATIONS = [
    ("photos", "original_path", "ALTER TABLE photos ADD COLUMN original_path TEXT NOT NULL DEFAULT ''"),
    ("photos", "preview_path", "ALTER TABLE photos ADD COLUMN preview_path TEXT"),
    ...
    ("groups", "close_call", "ALTER TABLE groups ADD COLUMN close_call INTEGER NOT NULL DEFAULT 0"),
    ("analyses", "group_idx", "ALTER TABLE analyses ADD COLUMN group_idx INTEGER"),
    ("analyses", "in_group_order", "ALTER TABLE analyses ADD COLUMN in_group_order INTEGER"),
    ("analyses", "suggested", "ALTER TABLE analyses ADD COLUMN suggested INTEGER NOT NULL DEFAULT 0"),
]
```

Note that **`NOT NULL` columns carry a `DEFAULT`** (`''`, `0`). SQLite refuses to add a `NOT NULL`
column to a table with existing rows unless a default is supplied — existing rows need a value. The
`DEFAULT` is also the sensible value for those pre-existing rows.

### Data migration (the `user_version < N` block)

Adding a column is sometimes not enough — existing rows may need their **values** recomputed. That's a
data migration, gated on `PRAGMA user_version` so it runs exactly once, on the first open after the
upgrade past that version:

```python
version = conn.execute("PRAGMA user_version").fetchone()[0]
if version < 2:
    # v2: a single-shot group's only frame is now a suggested pick (it earns the ✨ badge and is
    # included by "Accept picks"). Older DBs persisted suggested=0 for single shots — backfill the
    # sole frame of every single-member group. Idempotent (guarded by suggested=0).
    conn.execute(
        "UPDATE analyses SET suggested = 1 "
        "WHERE suggested = 0 AND in_group_order = 0 AND photo_id IN ("
        "  SELECT a.photo_id FROM analyses a JOIN photos p ON p.id = a.photo_id "
        "  WHERE a.group_idx IS NOT NULL "
        "  GROUP BY p.session_id, a.group_idx HAVING COUNT(*) = 1"
        ")"
    )

conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
```

The v2 migration backfills the `suggested` flag for the sole frame of every single-member group, so
those single shots get the ✨ badge and are picked up by "Accept picks" — without touching multi-shot
bursts. The final `PRAGMA user_version = _SCHEMA_VERSION` stamps the DB so neither the column pass nor
the data block re-runs on the next open.

## Recipe: add a new column

1. **Add the column to `_SCHEMA`.** Put it on the table's `CREATE TABLE` so fresh DBs get it.
2. **Add the matching `ALTER` to `_COLUMN_MIGRATIONS`** — a `(table, column, ddl)` tuple. Keep the
   column type/default identical to what you put in `_SCHEMA`. A `NOT NULL` column **must** carry a
   `DEFAULT` (a non-`NULL`, sensible value), or the `ALTER` fails on a DB that already has rows.
3. **Bump `_SCHEMA_VERSION`** by 1.
4. **If existing rows need a recomputed value**, add a `if version < <new>:` data-migration block
   before the final `PRAGMA user_version = _SCHEMA_VERSION` line (see safety rules below).
5. **Test against an old DB** (see Testing).

A brand-new **table** only needs step 1 — `CREATE TABLE IF NOT EXISTS` handles it. You still bump the
version if you also ship a data migration.

## Backfill pattern, idempotency, and safety

- **Column adds are inherently idempotent** — `_migrate()` checks `PRAGMA table_info` first and skips
  the `ALTER` if the column already exists. Don't worry about an `ALTER` running twice.
- **Write data migrations so they are safe even if re-run.** The version gate (`if version < N`)
  already makes them run once per upgrade, but guard the `UPDATE`/`INSERT` itself too (the v2 query
  only touches rows where `suggested = 0`). This is belt-and-suspenders against a half-applied
  migration (e.g. a crash before `commit`).
- **Never use a `NULL` default for a `NOT NULL` column.** Existing rows need a real value; pick the
  one that's correct for already-ingested data.
- **Migrations only ever ADD** — add columns, add tables, backfill values. Don't drop or rename
  columns in a migration; SQLite's `ALTER` support is limited and a destructive change can corrupt or
  lose a user's decisions.
- **Never change or delete an old migration entry or an old `if version < …` block.** A user may
  upgrade across several versions at once, so every historical migration must still apply in order.
  Old entries are immutable history; only append new ones.
- **Append at the end.** New `_COLUMN_MIGRATIONS` tuples and new version blocks go after the existing
  ones, in ascending version order.

## Testing

Cover new migrations the same way the existing ones are tested in `tests/test_store.py`:

- **`test_migrate_self_heals_old_schema`** — hand-builds an *old* DB (a `CREATE TABLE` missing the
  newer columns), inserts a row, opens it with `CullStore(db)`, then asserts the new columns exist,
  `user_version == _SCHEMA_VERSION`, the pre-existing row survived, and the DB works end-to-end. Add
  your new column to that assertion when you add it.
- **`test_migrate_is_idempotent_on_current_schema`** — opens a current-schema DB twice; the second
  open must not error (every column already present).
- **For a data migration**, follow `test_migrate_v2_backfills_single_shot_suggested`: seed the rows,
  force the DB back to the prior version with `PRAGMA user_version = <old>`, reopen with `CullStore`,
  and assert the backfill ran (and left out-of-scope rows untouched).

Quick manual check: copy a real old DB (`cp ~/.photo-cherrypick-desktop/cull.db /tmp/old.db`), point
the app or a `CullStore("/tmp/old.db")` at the copy, and confirm it opens, migrates, and keeps the
existing sessions/decisions.
