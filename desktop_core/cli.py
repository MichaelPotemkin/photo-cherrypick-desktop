"""Headless culling CLI — also the primary evaluation harness.

    python -m desktop_core.cli cull <folder> [--db PATH] [--cache DIR]
                                             [--export DEST] [--auto-favorite] [--json OUT]

Runs the full local pipeline on a folder (no server, no network beyond first-run model weights)
and prints a per-group summary. `--auto-favorite` marks each group's suggested pick and exports,
to exercise the decision + export path end-to-end.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from . import export as export_mod
from .ingest import scan_folder
from .pipeline_runner import run_session, warmup
from .store import CullStore
from .views import groups_response


def _progress(done: int, total: int) -> None:
    bar = int(30 * done / total) if total else 0
    print(f"\r  analyzing {done}/{total} [{'#' * bar}{'.' * (30 - bar)}]", end="", file=sys.stderr)
    if done == total:
        print(file=sys.stderr)


def cmd_cull(args: argparse.Namespace) -> int:
    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 2

    items = scan_folder(folder)
    print(f"found {len(items)} photo(s) (RAW+JPEG paired) in {folder}", file=sys.stderr)
    if not items:
        return 1

    db_path = args.db or str(Path(tempfile.mkdtemp(prefix="cull_")) / "cull.db")
    cache_dir = args.cache or str(Path(tempfile.mkdtemp(prefix="cull_cache_")))
    store = CullStore(db_path)
    sid = store.create_session(str(folder))

    print("warming up models…", file=sys.stderr)
    t0 = time.time()
    warmup()
    print(f"  warmup {time.time() - t0:.1f}s", file=sys.stderr)

    t0 = time.time()
    summary = run_session(store, sid, items, cache_dir, on_progress=_progress)
    dt = time.time() - t0
    per = dt / max(1, summary["analyzed"])
    print(
        f"analyzed {summary['analyzed']} in {dt:.1f}s ({per:.2f}s/photo), "
        f"{summary['groups']} groups, {len(summary['unsupported'])} unsupported",
        file=sys.stderr,
    )

    data = groups_response(store, sid)
    multi = [g for g in data["groups"] if len(g["photos"]) > 1]
    print(f"\n=== {len(data['groups'])} groups ({len(multi)} multi-shot bursts) ===")
    for g in data["groups"][:20]:
        pick = next((p for p in g["photos"] if p["suggested"]), g["photos"][0])
        tag = "★" if any(p["suggested"] for p in g["photos"]) else " "
        print(f"[{g['idx']:>3}] {tag} {g['label']:<22} "
              f"best={pick['filename']} score={pick['overall']:.3f} "
              f"reasons={', '.join(pick['reasons']) or '-'}")

    if args.auto_favorite:
        for g in data["groups"]:
            pick = next((p for p in g["photos"] if p["suggested"]), None) or g["photos"][0]
            store.add_decision(sid, pick["id"], "favorite")
        print(f"\nauto-favorited {len(data['groups'])} suggested picks", file=sys.stderr)

    if args.export:
        res = export_mod.export_to_folder(store, sid, args.export, move=False)
        print(f"exported -> {res}", file=sys.stderr)

    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "groups": data["groups"]}, indent=2))
        print(f"wrote {args.json}", file=sys.stderr)

    print(f"\ndb: {db_path}\ncache: {cache_dir}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="desktop_core.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cull", help="cull a local folder")
    c.add_argument("folder")
    c.add_argument("--db")
    c.add_argument("--cache")
    c.add_argument("--export")
    c.add_argument("--auto-favorite", action="store_true")
    c.add_argument("--json")
    c.set_defaults(func=cmd_cull)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
