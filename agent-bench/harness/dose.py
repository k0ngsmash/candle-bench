"""Did the cap actually bite, and when it did, did it matter? Paired, per task.

P1-P3 compared capped and full-history arms and found no difference - but the run summaries show
the cap removed little or nothing in the median task (e.g. "kept 24 of 24 turns"). This script
measures the treatment each task actually received and compares outcomes *where it was applied*.

For every capped run it reads calls.jsonl (per-call policy stats: turns_total, turns_kept,
tokens_before, tokens_after) and maps each call to its task via the same conversation tag the
proxy uses (sha1 of the first user message). Per task it records:
  dropped_max   most turns removed on any single call
  frac_max      largest fraction of the history removed on any call
  bitten        dropped_max > 0
and joins the task's outcome (resolved from summary.json, looped_3 / ccycled_3 from the trajectory).

Then, per capped arm, it compares against a reference arm (full history) on the SAME tasks:
  - capped resolve / loop rate, split into bitten vs not-bitten tasks
  - the reference arm's rate on exactly the tasks that were bitten (paired, averaged over seeds)
  - a dose table: tasks binned by frac_max

  python dose.py --ref 'runs/*p1-armA-s*' --arm 'Bhard2=runs/*p2-Bhard2-s*' --arm 'Chard2=runs/*p2-Chard2-s*'
"""
import argparse
import glob
import hashlib
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loopmetrics import actions_from_traj, loop_metrics  # noqa: E402


def conv_tag(traj: dict):
    for m in traj.get("messages", []):
        if m.get("role") == "user":
            c = m.get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            return hashlib.sha1(text.encode()).hexdigest()[:10]
    return None


def run_tasks(run_dir: Path) -> dict:
    """task -> {resolved, looped, cycled, dropped_max, frac_max, calls}"""
    s = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
    resolved = set((s.get("score") or {}).get("resolved_ids") or [])
    graded = bool(s.get("score"))
    by_conv = defaultdict(list)
    if (run_dir / "calls.jsonl").exists():
        for line in open(run_dir / "calls.jsonl"):
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if c.get("kind") == "summary" or not c.get("policy"):
                continue
            by_conv[c.get("conv")].append(c["policy"])
    out = {}
    for traj in sorted((run_dir / "agent").glob("*/*.traj.json")):
        try:
            d = json.loads(traj.read_text())
        except ValueError:
            continue
        task = traj.parent.name
        m = loop_metrics(actions_from_traj(d), 3)
        pol = by_conv.get(conv_tag(d), [])
        dropped = [p["turns_total"] - p["turns_kept"] for p in pol]
        fracs = [(p["turns_total"] - p["turns_kept"]) / p["turns_total"] for p in pol if p.get("turns_total")]
        out[task] = {"resolved": (task in resolved) if graded else None, "looped": m["looped_3"],
                     "exit": (d.get("info") or {}).get("exit_status"),
                     "cycled": m.get("ccycled_3"), "dropped_max": max(dropped) if dropped else 0,
                     "frac_max": max(fracs) if fracs else 0.0, "calls": len(pol)}
    return out


def pool(pattern: str) -> dict:
    """task -> list of per-seed records, over every run dir matching the glob."""
    pooled = defaultdict(list)
    dirs = sorted(Path(p) for p in glob.glob(pattern) if Path(p).is_dir())
    for d in dirs:
        for t, r in run_tasks(d).items():
            pooled[t].append(r)
    return pooled, dirs


def rate(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)


def fmt(r):
    v, n = r
    return f"{v:.0%} (n={n})" if v is not None else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", required=True, help="glob of reference (full-history) run dirs")
    ap.add_argument("--arm", action="append", required=True, metavar="NAME=GLOB")
    ap.add_argument("--json", metavar="FILE", help="also write the per-task table here")
    a = ap.parse_args()
    ref, ref_dirs = pool(a.ref)
    print(f"reference: {len(ref_dirs)} runs, {len(ref)} tasks  ({a.ref})")
    ref_res = {t: rate([r["resolved"] for r in rs])[0] for t, rs in ref.items()}
    ref_loop = {t: rate([r["looped"] for r in rs])[0] for t, rs in ref.items()}
    dump = {}
    for spec in a.arm:
        name, pattern = spec.split("=", 1)
        arm, dirs = pool(pattern)
        recs = [(t, r) for t, rs in arm.items() for r in rs]
        bit = [(t, r) for t, r in recs if r["dropped_max"] > 0]
        nob = [(t, r) for t, r in recs if r["dropped_max"] == 0]
        print(f"\n== {name}: {len(dirs)} runs, {len(recs)} task-runs; cap bit in {len(bit)} ({len(bit) / max(len(recs), 1):.0%})")
        if bit:
            print(f"   turns removed when it bit: median {st.median(r['dropped_max'] for _, r in bit)}, "
                  f"max {max(r['dropped_max'] for _, r in bit)}; share of history removed median "
                  f"{st.median(r['frac_max'] for _, r in bit):.0%}")
        print(f"   resolved   capped & bitten {fmt(rate([r['resolved'] for _, r in bit]))}  |  capped & not bitten "
              f"{fmt(rate([r['resolved'] for _, r in nob]))}  |  SAME tasks with full history "
              f"{fmt(rate([ref_res.get(t) for t, _ in bit]))}")
        print(f"   looped     capped & bitten {fmt(rate([r['looped'] for _, r in bit]))}  |  capped & not bitten "
              f"{fmt(rate([r['looped'] for _, r in nob]))}  |  SAME tasks with full history "
              f"{fmt(rate([ref_loop.get(t) for t, _ in bit]))}")
        print("   dose (share of history removed) -> capped resolved vs same-task full-history resolved:")
        for lo, hi in ((0, 0), (1e-9, .25), (.25, .5), (.5, .75), (.75, 1.01)):
            cell = [(t, r) for t, r in recs if (r["frac_max"] == 0 if hi == 0 else lo <= r["frac_max"] < hi)]
            if cell:
                lab = "none" if hi == 0 else f"{lo:.0%}-{min(hi, 1):.0%}"
                print(f"     {lab:>9}: n={len(cell):3d}  capped {fmt(rate([r['resolved'] for _, r in cell]))}  "
                      f"full {fmt(rate([ref_res.get(t) for t, _ in cell]))}")
        dump[name] = {t: r for t, r in recs}
    if a.json:
        Path(a.json).write_text(json.dumps(dump, indent=1, default=str))


if __name__ == "__main__":
    main()
