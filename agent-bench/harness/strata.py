"""Does cutting history hurt more on harder tasks? Outcomes by task difficulty, capped vs full history.

Difficulty is measured independently of our agent, from the benchmark itself:
  difficulty   SWE-bench Verified's human estimate of time-to-fix (<15 min, 15 min-1 h, 1-4 h, >4 h)
  files        files touched by the gold patch (1, 2+)
  lines        lines added + removed by the gold patch (<=5, 6-20, >20)
Tasks not in Verified (some stuck-15 tasks come from Lite) get files/lines only.

For each grouping it prints, per bucket: tasks, the reference (full history) and each capped arm's
resolve rate over task-runs, the difference, a two-sided Fisher exact p, and for the capped arm the
share of task-runs where the cap bit and the share that hit the step limit.

  python strata.py --ref 'runs/*_p3-A150_vllm_w8' --arm 'hard8K-recency=runs/*_p5-B150-8k_*'
"""
import argparse
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dose import pool  # noqa: E402

DIFF_ORDER = ["<15 min fix", "15 min - 1 hour", "1-4 hours", ">4 hours"]


def fisher_p(a, n1, b, n2):
    """Two-sided Fisher exact test for a/n1 vs b/n2 (sum of tables no more likely than the observed)."""
    k, n = a + b, n1 + n2
    if n1 == 0 or n2 == 0:
        return None
    denom = comb(n, k)
    prob = lambda x: comb(n1, x) * comb(n2, k - x) / denom
    obs = prob(a)
    return min(1.0, sum(prob(x) for x in range(max(0, k - n2), min(k, n1) + 1) if prob(x) <= obs * (1 + 1e-9)))


def patch_size(patch: str):
    files, lines = 0, 0
    for l in (patch or "").splitlines():
        if l.startswith("diff --git"):
            files += 1
        elif (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")):
            lines += 1
    return files, lines


def load_meta():
    from datasets import load_dataset
    meta = {}
    for name in ("princeton-nlp/SWE-bench_Lite", "SWE-bench/SWE-bench_Verified"):   # Verified wins on overlap
        try:
            ds = load_dataset(name, split="test")
        except Exception as e:  # noqa: BLE001
            print(f"(could not load {name}: {e})")
            continue
        for r in ds:
            f, l = patch_size(r.get("patch"))
            m = meta.setdefault(r["instance_id"], {})
            m.update(files="1 file" if f <= 1 else "2+ files",
                     lines="<=5 lines" if l <= 5 else ("6-20 lines" if l <= 20 else ">20 lines"))
            if r.get("difficulty"):
                m["difficulty"] = r["difficulty"]
    return meta


def rate(recs, key):
    xs = [r[key] for r in recs if r.get(key) is not None]
    return sum(bool(x) for x in xs), len(xs)


def pct(k, n):
    return f"{k / n:4.0%} ({k}/{n})" if n else "   n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", required=True)
    ap.add_argument("--arm", action="append", required=True, metavar="NAME=GLOB")
    a = ap.parse_args()
    meta = load_meta()
    ref, ref_dirs = pool(a.ref)
    arms = []
    for spec in a.arm:
        name, pattern = spec.split("=", 1)
        arm, dirs = pool(pattern)
        arms.append((name, arm, len(dirs)))
    print(f"reference: {len(ref_dirs)} runs, {len(ref)} tasks ({a.ref}); metadata for "
          f"{sum(t in meta for t in ref)} of them, difficulty for {sum('difficulty' in meta.get(t, {}) for t in ref)}")
    for key in ("difficulty", "files", "lines"):
        buckets = {}
        for t in ref:
            b = meta.get(t, {}).get(key)
            if b:
                buckets.setdefault(b, []).append(t)
        if not buckets:
            print(f"\n-- by {key}: no metadata")
            continue
        order = [b for b in DIFF_ORDER if b in buckets] if key == "difficulty" else sorted(buckets)
        print(f"\n-- by {key}")
        for name, arm, nd in arms:
            print(f"   {name} ({nd} runs) vs full history")
            print(f"     {'bucket':<16}{'tasks':>6}  {'full history':<16}{name[:16]:<16}{'diff':>6}  {'p':>6}   cap bit   step limit")
            for b in order:
                ts = buckets[b]
                rr = [r for t in ts for r in ref.get(t, [])]
                ar = [r for t in ts for r in arm.get(t, [])]
                rk, rn = rate(rr, "resolved")
                ak, an = rate(ar, "resolved")
                p = fisher_p(ak, an, rk, rn)
                bit = sum(r["dropped_max"] > 0 for r in ar)
                lim = sum(r.get("exit") == "LimitsExceeded" for r in ar)
                diff = f"{(ak / an - rk / rn) * 100:+5.0f}" if an and rn else "   - "
                print(f"     {b:<16}{len(ts):>6}  {pct(rk, rn):<16}{pct(ak, an):<16}{diff:>6}  "
                      f"{(f'{p:.3f}' if p is not None else '-'):>6}   {pct(bit, len(ar)):<10}{pct(lim, len(ar))}")


if __name__ == "__main__":
    main()
