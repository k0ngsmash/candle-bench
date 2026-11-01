"""The looping metric, defined precisely, plus a per-step reliability fit.

Why this exists: three recent papers name "the agent gets stuck in a loop" as a primary long-horizon
failure and none of them measure it (two filter looping runs out of their data). This module turns
it into numbers computed from a mini-swe-agent trajectory, so looping can be reported as a
mechanism alongside the usual outcome (graded solve rate).

Definitions (per task)
----------------------
An *action* is the `command` string of one bash tool call the agent issued, normalised by stripping
and collapsing whitespace. Let a_1..a_n be the action sequence.

  n_actions        n
  n_distinct       number of distinct actions
  max_repeat       the multiplicity of the most-issued action
  repeat_fraction  (n - n_distinct) / n  - share of actions that re-issue an earlier one
  longest_run      longest run of consecutive identical actions (the tight loop)
  loop_onset_k     1-based step at which some action is issued for the k-th time (None if never);
                   k=3 is the headline ("issued the same thing three times"), k=2 is noisy (ls twice)
  looped_k         loop_onset_k is not None
  looped_5plus     max_repeat >= 5  - kept for continuity with earlier result tables

Run level
---------
Means/medians of the above, the share of tasks that looped, and - when graded outcomes are present -
a per-step reliability r fitted to the geometric model P(success | h steps) = r**h by maximum
likelihood. This is the *observed-steps* variant of the agent-rot paper's model (they use the task's
intrinsic horizon; we use the steps the agent actually took), so it is comparable in form, not in
absolute value. It is reported as a secondary number for exactly that reason.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

_WS = re.compile(r"\s+")


def normalise(cmd: str) -> str:
    return _WS.sub(" ", cmd.strip())


def actions_from_traj(d: dict) -> list[str]:
    out = []
    for m in d.get("messages", []):
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            try:
                args = tc["function"]["arguments"]
                args = json.loads(args) if isinstance(args, str) else args
                cmd = args.get("command")
            except (ValueError, KeyError, TypeError, AttributeError):
                cmd = None
            if isinstance(cmd, str) and cmd.strip():
                out.append(normalise(cmd))
    return out


def loop_metrics(actions: list[str], k: int = 3) -> dict:
    n = len(actions)
    if n == 0:
        return {"n_actions": 0, "n_distinct": 0, "max_repeat": 0, "repeat_fraction": 0.0, "longest_run": 0,
                "loop_onset_2": None, f"loop_onset_{k}": None, f"looped_{k}": False, "looped_5plus": False}
    counts = Counter(actions)
    # longest run of consecutive identical actions
    longest = run = 1
    for i in range(1, n):
        run = run + 1 if actions[i] == actions[i - 1] else 1
        longest = max(longest, run)
    # onset: first step at which any action reaches its k-th occurrence
    seen: Counter = Counter()
    onset = {2: None, k: None}
    for i, a in enumerate(actions, 1):
        seen[a] += 1
        for kk in onset:
            if onset[kk] is None and seen[a] == kk:
                onset[kk] = i
    return {
        "n_actions": n, "n_distinct": len(counts), "max_repeat": max(counts.values()),
        "repeat_fraction": round((n - len(counts)) / n, 4), "longest_run": longest,
        "loop_onset_2": onset[2], f"loop_onset_{k}": onset[k],
        f"looped_{k}": onset[k] is not None, "looped_5plus": max(counts.values()) >= 5,
    }


def fit_per_step_reliability(outcomes: Iterable[tuple[bool, int]]) -> Optional[dict]:
    """MLE of r in P(success | h) = r**h, by golden-section search on the log-likelihood."""
    data = [(bool(s), int(h)) for s, h in outcomes if h and h > 0]
    if not data or all(s for s, _ in data) or not any(s for s, _ in data):
        return None  # degenerate: no information about r in the interior

    def ll(r):
        tot = 0.0
        for s, h in data:
            p = r ** h
            tot += math.log(max(p, 1e-300)) if s else math.log(max(1 - p, 1e-300))
        return tot

    lo, hi = 1e-6, 1 - 1e-6
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = ll(a), ll(b)
    for _ in range(200):
        if fa > fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo); fa = ll(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo); fb = ll(b)
    r = (lo + hi) / 2
    return {"r": round(r, 4), "n": len(data), "loglik": round(ll(r), 2),
            "median_steps": st.median(h for _, h in data)}


def analyse_run(run_dir: Path, k: int = 3) -> dict:
    """Per-task rows + run-level aggregate. Writes loop.csv next to summary.json."""
    summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
    resolved = set((summary.get("score") or {}).get("resolved_ids") or [])
    graded = bool(summary.get("score"))
    rows = []
    for traj in sorted((run_dir / "agent").glob("*/*.traj.json")):
        try:
            d = json.loads(traj.read_text())
        except ValueError:
            continue
        task = traj.parent.name
        acts = actions_from_traj(d)
        m = loop_metrics(acts, k)
        m.update(task=task, exit_status=(d.get("info") or {}).get("exit_status"),
                 resolved=(task in resolved) if graded else None)
        rows.append(m)
    if rows:
        with open(run_dir / "loop.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    agg = aggregate(rows, k)
    if graded:
        agg["per_step_reliability"] = fit_per_step_reliability((r["resolved"], r["n_actions"]) for r in rows)
    return {"k": k, "tasks": len(rows), "rows": rows, "aggregate": agg}


def aggregate(rows: list[dict], k: int = 3) -> dict:
    if not rows:
        return {}
    def med(key):
        xs = [r[key] for r in rows if r.get(key) is not None]
        return st.median(xs) if xs else None
    n = len(rows)
    return {
        "max_repeat_median": med("max_repeat"),
        "repeat_fraction_mean": round(st.mean(r["repeat_fraction"] for r in rows), 4),
        "longest_run_median": med("longest_run"),
        f"loop_onset_{k}_median": med(f"loop_onset_{k}"),
        f"tasks_looped_{k}": sum(1 for r in rows if r[f"looped_{k}"]),
        "tasks_looped_5plus": sum(1 for r in rows if r["looped_5plus"]),
        f"loop_rate_{k}": round(sum(1 for r in rows if r[f"looped_{k}"]) / n, 3),
        "n_actions_median": med("n_actions"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", nargs="+")
    ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for rd in a.run_dir:
        res = analyse_run(Path(rd), a.k)
        if a.json:
            print(json.dumps({"run": rd, **{x: res[x] for x in ("k", "tasks", "aggregate")}}, indent=1))
        else:
            ag = res["aggregate"]
            print(f"{Path(rd).name}: {res['tasks']} tasks | looped(k={a.k}) {ag.get(f'tasks_looped_{a.k}')} "
                  f"| 5+ {ag.get('tasks_looped_5plus')} | max_repeat med {ag.get('max_repeat_median')} "
                  f"| repeat_frac {ag.get('repeat_fraction_mean')} | longest_run med {ag.get('longest_run_median')} "
                  f"| onset med {ag.get(f'loop_onset_{a.k}_median')}"
                  + (f" | r={ag['per_step_reliability']['r']}" if ag.get("per_step_reliability") else ""))


if __name__ == "__main__":
    main()
