"""Fast OFFLINE re-scoring of the cached gallery — test scoring changes in milliseconds.

Re-runs compute_refs + the in-burst pick logic over the dumped per-photo metas (no torch, no
re-analysis). Edit pipeline/score.py (or pipeline/select.py), re-run this, and see how the picks
change. Burst membership is fixed (it's score-independent), so this isolates pick quality.

Usage:
    python eval/rescore.py                 # print per-group picks + close flags
    python eval/rescore.py --compare REF   # compare picks to a reference json {group_idx: pick_filename}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.score import axis_scores, compute_refs   # noqa: E402
from pipeline.select import rank_burst                  # noqa: E402

CLOSE_GAP = 0.05   # keep in sync with desktop_core.pipeline_runner._CLOSE_GAP


def score_groups(path="/tmp/eval_metas.json") -> dict:
    d = json.load(open(path))
    all_metas = [ph["meta"] for g in d["all_groups"].values() for ph in g]
    refs = compute_refs(all_metas)
    out = {}
    for gi, photos in d["multi"].items():
        metas = [p["meta"] for p in photos]
        order = rank_burst(metas, refs)
        ranked = [(photos[i]["filename"], axis_scores(metas[i], refs)[2]) for i in order]
        gap = ranked[0][1] - ranked[1][1]
        out[gi] = {
            "pick": ranked[0][0],
            "ranking": ranked,
            "gap": gap,
            "close": gap < CLOSE_GAP,
            "n": len(photos),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metas", default="/tmp/eval_metas.json")
    ap.add_argument("--compare", help="reference json {group_idx: pick_filename}")
    args = ap.parse_args()
    res = score_groups(args.metas)

    if args.compare:
        ref = json.load(open(args.compare))
        agree = clear_agree = clear_total = 0
        misses = []
        for gi, r in res.items():
            if gi not in ref:
                continue
            ok = r["pick"] == ref[gi]
            agree += ok
            if not r["close"]:
                clear_total += 1
                clear_agree += ok
                if not ok:
                    misses.append((gi, r["pick"], ref[gi], round(r["gap"], 3)))
        n = sum(1 for gi in res if gi in ref)
        print(f"agreement: {agree}/{n} ({agree/n*100:.0f}%)   "
              f"clear-margin agreement: {clear_agree}/{clear_total} "
              f"({(clear_agree/clear_total*100 if clear_total else 0):.0f}%)")
        print(f"clear-margin misses ({len(misses)}):")
        for gi, pick, want, gap in sorted(misses):
            print(f"   grp {gi}: picked {pick}  ref wants {want}  (gap {gap})")
    else:
        close = sum(1 for r in res.values() if r["close"])
        print(f"{len(res)} multi-photo groups, {close} close-calls")
        for gi, r in sorted(res.items(), key=lambda kv: int(kv[0])):
            flag = " [close]" if r["close"] else ""
            print(f"  grp {gi}: {r['pick']}  gap={r['gap']:.3f}{flag}")


if __name__ == "__main__":
    main()
