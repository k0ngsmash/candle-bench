"""Summarise one run directory into summary.md (and fold the numbers into summary.json)."""
import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def main(run_dir: Path):
    s = json.loads((run_dir / "summary.json").read_text())
    calls = [json.loads(l) for l in open(run_dir / "calls.jsonl")] if (run_dir / "calls.jsonl").exists() else []
    ok = [c for c in calls if c["status"] == 200]
    by_conv = defaultdict(list)
    for c in ok:
        by_conv[c["conv"]].append(c)

    comp = sum(c["completion_tokens"] or 0 for c in ok)
    prompt = sum(c["prompt_tokens"] or 0 for c in ok)
    secs = [c["seconds"] for c in ok]
    rates = [c["completion_tokens"] / c["seconds"] for c in ok if c["completion_tokens"] and c["seconds"] > 0]
    peaks = [max(c["prompt_tokens"] or 0 for c in v) for v in by_conv.values()]
    task_wall = [max(c["t_start"] + c["seconds"] for c in v) - min(c["t_start"] for c in v) for v in by_conv.values()]
    gen_busy = sum(secs)

    exits = defaultdict(int)
    for traj in (run_dir / "agent").glob("*/*.traj.json"):
        try:
            info = json.loads(traj.read_text()).get("info", {})
            exits[info.get("exit_status", "unknown")] += 1
        except ValueError:
            exits["unreadable"] += 1

    gpu = list(csv.DictReader(open(run_dir / "gpu.csv"))) if (run_dir / "gpu.csv").exists() else []
    util = [float(r["util_pct"]) for r in gpu if r.get("util_pct", "").replace(".", "").isdigit()]
    mem = [float(r["mem_used_mib"]) for r in gpu if r.get("mem_used_mib", "").replace(".", "").isdigit()]

    m = {
        "model_calls": len(calls), "failed_calls": len(calls) - len(ok),
        "prompt_tokens_total": prompt, "completion_tokens_total": comp,
        "call_seconds_median": round(st.median(secs), 2) if secs else None,
        "call_seconds_p90": round(pct(secs, 90), 2) if secs else None,
        "decode_tps_per_call_median": round(st.median(rates), 1) if rates else None,
        "completion_tps_aggregate": round(comp / s["wall_seconds"], 1) if s["wall_seconds"] else None,
        "steps_per_task_median": st.median(len(v) for v in by_conv.values()) if by_conv else None,
        "task_minutes_median": round(st.median(task_wall) / 60, 1) if task_wall else None,
        "context_peak_tokens_median": int(st.median(peaks)) if peaks else None,
        "context_peak_tokens_max": max(peaks) if peaks else None,
        "gpu_util_mean_pct": round(st.mean(util), 1) if util else None,
        "gpu_mem_peak_mib": max(mem) if mem else None,
        "exit_statuses": dict(exits),
        "model_busy_seconds": round(gen_busy),
    }
    s["metrics"] = m
    (run_dir / "summary.json").write_text(json.dumps(s, indent=1))

    score = s.get("score") or {}
    lines = [f"# {run_dir.name}", "",
             f"- Backend: **{s['backend']}**, {s['workers']} parallel agents, {s['tasks']} tasks",
             f"- Resolved: **{score.get('resolved', '?')} / {s['tasks']}** (submitted {score.get('submitted', '?')})",
             f"- Wall time: {s['wall_seconds']/60:.1f} min; median task {m['task_minutes_median']} min, "
             f"{m['steps_per_task_median']} model calls",
             f"- Model calls: {m['model_calls']} ({m['failed_calls']} failed); median {m['call_seconds_median']} s, p90 {m['call_seconds_p90']} s",
             f"- Tokens: {prompt:,} prompt, {comp:,} generated; generation {m['completion_tps_aggregate']} t/s across the run, "
             f"{m['decode_tps_per_call_median']} t/s per call (median)",
             f"- Context per task: median peak {m['context_peak_tokens_median']:,} tokens, largest {m['context_peak_tokens_max']:,}" if peaks else "- Context: n/a",
             f"- GPU: mean utilisation {m['gpu_util_mean_pct']}%, peak memory {m['gpu_mem_peak_mib']} MiB",
             f"- Agent exits: {dict(exits)}"]
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
