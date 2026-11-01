"""Pick the P2 replication slice: N instances of SWE-bench Verified, stratified by repo, fixed seed.

Deterministic: the same (N, seed) gives the same list on any machine with the dataset. Instances that
are in the stuck-15 are excluded so the replication set is independent of the sample the hypotheses
were formed on. Writes agent-bench/verified<N>.txt (one instance id per line) and prints the repo mix.

    ~/venvs/agent/bin/python pick_verified.py --n 150 --seed 0
"""
import argparse
import random
from collections import Counter, defaultdict
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude", default=str(BENCH / "stuck15.txt"))
    a = ap.parse_args()
    from datasets import load_dataset
    ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    exclude = set(Path(a.exclude).read_text().split()) if Path(a.exclude).exists() else set()
    by_repo = defaultdict(list)
    for row in ds:
        if row["instance_id"] not in exclude:
            by_repo[row["repo"]].append(row["instance_id"])
    total = sum(len(v) for v in by_repo.values())
    rng = random.Random(a.seed)
    # proportional allocation (largest remainder), at least 1 per repo that has any
    quota = {r: a.n * len(v) / total for r, v in by_repo.items()}
    take = {r: int(q) for r, q in quota.items()}
    for r in sorted(quota, key=lambda r: quota[r] - take[r], reverse=True)[: a.n - sum(take.values())]:
        take[r] += 1
    chosen = []
    for r in sorted(by_repo):
        ids = sorted(by_repo[r]); rng.shuffle(ids)
        chosen += ids[: take[r]]
    chosen.sort()
    out = BENCH / f"verified{a.n}.txt"
    out.write_text("\n".join(chosen) + "\n")
    print(f"{len(chosen)} instances -> {out}  (seed {a.seed}, {len(exclude)} excluded)")
    for r, c in Counter(i.split("__")[0] for i in chosen).most_common():
        print(f"  {c:3d}  {r}")


if __name__ == "__main__":
    main()
