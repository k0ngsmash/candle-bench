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


_QUOTED = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", re.S)
_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n[\s\S]*?(?:^|\n)\s*\1\s*(?:\n|$)", re.M)
_PATHLIKE = re.compile(r"^(?:[\w.\-]*/)*[\w.\-]+\.[A-Za-z]{1,5}$|^/[\w./\-]+$")


def canonical(cmd: str) -> str:
    """Collapse a command to its *shape*: per pipeline segment, the program plus any path-like
    arguments; quoted strings, heredocs, numbers and flags dropped. Two commands that do the same
    kind of thing to the same files canonicalise alike even when their free text drifts, e.g.
      python -c "...# test the fix..."   and   python -c "...# test the issue..."   -> python -c
      sed -n '1163,1200p' a/b.py         and   sed -n '1180,1220p' a/b.py          -> sed a/b.py
    """
    s = _HEREDOC.sub(lambda m: m.group(2) + "\n", cmd)      # drop the body, keep e.g. the `> file` on the marker line
    # short, space-free literals (a sed range, a grep pattern) are arguments - keep them; anything
    # longer or with whitespace is free text / code and is what drifts between near-duplicates
    s = _QUOTED.sub(lambda m: m.group(0) if len(m.group(0)) <= 26 and not re.search(r"\s", m.group(0)) else " ", s)
    out = []
    for seg in re.split(r"\s*(?:&&|\|\||\||;|\n)\s*", s):
        toks = seg.split()
        if not toks:
            continue
        prog, rest = toks[0], toks[1:]
        keep = []
        for i, t in enumerate(rest):
            if t.startswith("-"):
                if t in ("-c", "-m", "-n", "-e"):
                    keep.append(t)                       # sub-command style flags carry meaning
                continue
            if "/" in t or _PATHLIKE.match(t) or t[0] in "'\"" or (i and rest[i - 1] == "-m"):
                keep.append(t)
        out.append(" ".join([prog, *keep]))
    return " && ".join(out) or normalise(cmd)


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


def cycle_metrics(actions: list[str], max_period: int = 6, k: int = 3) -> dict:
    """Detect repeated *subsequences* - the edit -> test -> edit -> test shape the P1 matrix showed.

    For each period p in 1..max_period, a position i is "lagged-equal" if a[i] == a[i-p]. A maximal run
    of L consecutive lagged-equal positions means the p-long pattern ending there occurred
    floor(L/p)+1 times in a row. Reported:

      cycle_period        the p of the strongest cycle (most repetitions; ties -> shorter period)
      cycle_repeats_max   how many times that pattern occurred consecutively (>=2 means a real cycle)
      cycle_onset         1-based step at which the strongest cycle first completed its 2nd repetition
      cycled_k            some pattern (any period) repeated >= k times consecutively - the cycle
                          analogue of looped_k, and strictly stronger (consecutive, not just re-issued)
      cycle_fraction      share of actions that sit inside any detected cycle (period >= 1, >= 2 reps)

    Period 1 is a stutter (same as longest_run); periods >= 2 are the cycles longest_run cannot see.
    """
    n = len(actions)
    best_period, best_reps = None, 1
    covered: set = set()
    for p in range(1, max_period + 1):
        if n < 2 * p:
            break
        run = 0
        for i in range(p, n):
            if actions[i] != actions[i - p]:
                run = 0
                continue
            run += 1
            reps = run // p + 1                      # full consecutive occurrences of the p-pattern
            if reps >= 2:
                covered.update(range(i - run - p + 1, i + 1))
                if reps > best_reps or (reps == best_reps and p < best_period):
                    best_period, best_reps = p, reps
    onset = None
    if best_period:  # first step at which the strongest cycle's pattern completed its 2nd occurrence
        p, run = best_period, 0
        for i in range(p, n):
            run = run + 1 if actions[i] == actions[i - p] else 0
            if run == p:
                onset = i + 1
                break
    return {"cycle_period": best_period, "cycle_repeats_max": best_reps if best_period else 0,
            "cycle_onset": onset, f"cycled_{k}": bool(best_period) and best_reps >= k,
            "cycle_fraction": round(len(covered) / n, 4) if n else 0.0}


def loop_metrics(actions: list[str], k: int = 3) -> dict:
    n = len(actions)
    if n == 0:
        return {"n_actions": 0, "n_distinct": 0, "max_repeat": 0, "repeat_fraction": 0.0, "longest_run": 0,
                "loop_onset_2": None, f"loop_onset_{k}": None, f"looped_{k}": False, "looped_5plus": False,
                **cycle_metrics([], k=k), **{"c" + kk: v for kk, v in cycle_metrics([], k=k).items()}}
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
        **cycle_metrics(actions, k=k),                                                   # exact
        **{"c" + kk: v for kk, v in cycle_metrics([canonical(a) for a in actions], k=k).items()},  # canonical shape
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
        f"tasks_cycled_{k}": sum(1 for r in rows if r.get(f"cycled_{k}")),
        "cycle_period_mode": Counter(r["cycle_period"] for r in rows if r.get("cycle_period")).most_common(1)[0][0]
                             if any(r.get("cycle_period") for r in rows) else None,
        "cycle_fraction_mean": round(st.mean(r.get("cycle_fraction", 0.0) for r in rows), 4),
        f"tasks_ccycled_{k}": sum(1 for r in rows if r.get(f"ccycled_{k}")),
        "ccycle_period_mode": Counter(r["ccycle_period"] for r in rows if r.get("ccycle_period")).most_common(1)[0][0]
                              if any(r.get("ccycle_period") for r in rows) else None,
        "ccycle_repeats_median": med("ccycle_repeats_max"),
        "ccycle_fraction_mean": round(st.mean(r.get("ccycle_fraction", 0.0) for r in rows), 4),
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
