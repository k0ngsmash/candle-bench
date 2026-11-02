# P3 — the reasoning question, a second Verified seed, and the ceiling at n = 150

**Date:** 2 Nov 2026 (07:00–14:30, unattended) · **Box:** same RTX PRO 6000 (96 GB) · **Model:** Qwen3.6-35B-A3B AWQ-4bit on vLLM 0.32.0 · **Agent:** mini-swe-agent 2.4.6, step limit 75 · **Grading:** SWE-bench harness

P2 left one live hypothesis — that the agent does better when it does *not* see its own earlier `reasoning_content` — and one caveat: the n = 150 verdict rested on a single seed. P3 adds a `--strip-reasoning` switch (past reasoning removed from the history, nothing else changed, any policy) and runs:

- **stuck-15 × 3 seeds:** A-strip (full attention, reasoning stripped) and Bsoft-strip (soft-32K recency, reasoning stripped) — the P1 arms with one variable changed.
- **verified150, 8 agents:** B and C hard-32K at a second seed; A150 (full attention, the Verified ceiling); A150-strip.

## Results

### stuck-15 (45 task-runs per cell)

| arm | resolved | looped (k=3) | engine peak (med / max) | wall / 15 tasks |
|---|---|---|---|---|
| A full attention (P1) | 12 | 21 | 33–42K / 73–79K | 14.5–17 min |
| **A, reasoning stripped** | **10** (1/5/4) | **20** (5/7/8) | 31–33K / 47–49K | 11.5–14 min |
| B soft-32K recency (P1) | 9 | 19 | 33–38K / 53–60K | 14–16 min |
| **B soft, reasoning stripped** | **13** (5/4/4) | **23** (8/7/8) | 30–31K / 36K | 11–12.5 min |

A-strip vs A: resolved p = 0.81, looped p = 1.0. B-strip vs B: p = 0.48 / 0.52.

### verified150 (150 task-runs per cell, 8 agents)

| arm | seed 1 | seed 2 | **pooled** | looped | step-limit | engine peak max | wall |
|---|---|---|---|---|---|---|---|
| B recency, hard 32K | 77 | 71 | **148/300 (49%)** | 96/300 (32%) | 52 | 37–39K | 70–74 min |
| C relevance, hard 32K | 79 | 76 | **155/300 (52%)** | 92/300 (31%) | 67 | 38K | 76–82 min |
| **A150 full attention** | 74 | – | **74/150 (49%)** | 49/150 (33%) | 31 | **104K** | 76.5 min |
| **A150, reasoning stripped** | 76 | – | **76/150 (51%)** | 59/150 (39%) | 43 | 64K | 73 min |

C vs B pooled: resolved p = 0.62, looped p = 0.79. A150 vs B pooled p = 1.0; vs C pooled p = 0.69. A150-strip vs A150: resolved p = 0.91, looped p = 0.28. All 900 Verified task-runs pooled: **453 resolved (50.3%), 296 looped (32.9%)** — the four arms are indistinguishable from one population.

Seed-to-seed swing on 150 tasks: 3–6 solves. Prompt tokens for the 150-task pass: A150 151M, A150-strip 128M (−15%); B/C hard ~129–135M.

## Conclusions

1. **The reasoning hypothesis is rejected.** Removing the agent's past reasoning from its history changes neither solves nor looping, on the stuck-15 (10 vs 12; 13 vs 9) or on Verified (76 vs 74). P2's hard-cap result was not about reasoning.
2. **No context manipulation tested moves the outcome.** Across P1–P3 — full history or a third of it; recency, bge-small relevance, or model-written compaction; soft or hard cap; reasoning in or out — every vLLM arm lands at 9–14 of 45 on the stuck-15 and 49–52% on Verified, with 31–39% of tasks looping. The agent with its *entire* history (peaks to 104K) does exactly as well as the agent with a hard 32K. For this agent on this model, context retention over 32K → unbounded is not a lever. H2 (what you keep) is rejected; the "how much" question is answered: not much, down to a third.
3. **Stripping reasoning is a cost win, not a quality one.** Same outcome; engine peaks 47–49K instead of 73–79K on the stuck-15, −15% prompt tokens on Verified, ~20% faster on the stuck-15. It also raised step-limit exits on Verified (43 vs 31) and halved canonical cycles (39 vs 85 of 150) — the agent repeats itself less but also submits less; neither reached significance. Worth adopting for throughput; not a fix for anything.
4. **Looping is the agent's, and it is stable.** ~33% of Verified tasks loop at every arm (H1 stands at n = 900): canonical period-1 cycles — the same *kind* of action re-issued with drifting text — invisible to exact-match counting (0–1 of 150). Whatever drives it is upstream of context: the agent loop (no stuck detection, no plan state), the model's policy, or sampling. Those are the levers P4 should pull, not retention.
5. **The one significant effect in the whole program is the engine.** zend loops in 67–78% of tasks at any window; vLLM on the same weights 31–47%. That is a statement about the zend build, not about retention, and the retention claims it motivated could not be tested within it.

## What this means for the plan

- The "unbounded context" line — tiering, KV-of-KV, provenance retention — was premised on context size or selection limiting the agent. On this evidence it does not, at least up to ~100K on a 35B MoE. That premise should be re-examined before more infrastructure goes into it.
- The publishable contribution is narrower and more interesting than hoped: a **negative result at scale** (n = 900 graded task-runs: retention strategy, budget and reasoning retention do not affect a coding agent's success or looping on SWE-bench Verified), plus the **looping metric** and the cycle shape that explains why prior counts under-reported it.
- P4 candidates, in order of expected information: (a) the same matrix on a second model family (is the null model-specific?); (b) stuck detection and plan state in the agent loop (does fixing the *loop* fix looping?); (c) sampling (temperature/seed) as the looping lever; (d) the step-count × window factorial (H3) — now cheap, since window is known not to matter.

## Caveats

- One model, one agent harness, one task family. The null may not transfer to a weaker model, a longer-horizon agent, or non-code tasks; (a) above is the test.
- 150 Verified tasks per cell is enough to see a 10-point effect, not a 3-point one. "No effect" means "nothing at the scale P1 suggested."
- verified150 excludes the stuck-15 and is stratified by repo; absolute solve rates are for this slice and harness, not a leaderboard number.
- A150 and A150-strip are single seeds.

Runs: `agent-bench/runs/2026-11-0[12]_*_p3-*` on the box; job logs `queue/logs/20261102-0[6-9]*_1[12][0-9]-p3-*` and `1[12]*_12[3-6]-p3-*`.
