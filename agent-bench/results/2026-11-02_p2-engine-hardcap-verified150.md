# P2 — engine control, true hard cap, and the n = 150 replication

**Date:** 1–2 Nov 2026 (overnight, unattended) · **Box:** same RTX PRO 6000 (96 GB) as P1 · **Model:** Qwen3.6-35B-A3B (AWQ-4bit on vLLM 0.32.0; zend's own build for arm E) · **Agent:** mini-swe-agent 2.4.6, step limit 75 · **Grading:** SWE-bench harness throughout

Three questions left open by P1, each with a run designed to settle it:

1. Is zend's looping an **engine** property or a **retention** one? → zend with a window that holds everything (256K), 3 seeds.
2. Does relevance beat recency when the budget is **actually** enforced? → both at a hard 32K, 3 seeds, after fixing the ruler (see below).
3. Does the P1 direction survive **n = 150**? → recency vs relevance, hard 32K, on a stratified SWE-bench Verified slice, 8 agents.

## The ruler correction that reshaped the night

Thinking models return their reasoning as a separate `reasoning_content` field; mini-swe-agent sends it back in the history and vLLM's chat template re-injects it, at 2–10K chars per step. The proxy's token ruler never looked at that field, so every "32K" budget in P1 and the first P2 hard-cap runs covered only the non-reasoning history — the engine saw roughly double (P1's 53–65K peaks; P2's first "hard cap" reaching 64K). Matched across B/C/D, so P1's within-engine comparison stands; wrong on the label. Fixed mid-night (`c226993`): reasoning is counted, and when a turn must be trimmed its past reasoning is clipped first. On the fixed ruler the engine-side peak sits at 37.0–38.7K for a 32K tiktoken budget (the ~1.15× Qwen/cl100k ratio) — the cap is real.

## Results

| Arm | Set | Resolved | Looped (k=3) | repeat frac | step-limit |
|---|---|---|---|---|---|
| **E zend, 256K window** (holds everything; peaks to 146K) | stuck-15 × 3 | **7/45** (4/1/2) | **31/45** (13/9/9) | .15 | 33 |
| *E zend 32K / 64K (P1, P1-ext)* | stuck-15 × 3 | *6 / 7* | *35 / 30* | *.18 / .20* | *35 / 31* |
| B recency, hard 32K, *old ruler* (non-reasoning cap) | stuck-15 × 3 | 15/45 (7/3/5) | 15/45 (5/6/4) | .06 | 15 |
| **B recency, hard 32K** (fixed ruler) | stuck-15 × 3 | **13/45** (5/3/5) | **19/45** (7/8/4) | .08 | 14 |
| **C relevance, hard 32K** (fixed ruler) | stuck-15 × 3 | **14/45** (6/3/5) | **24/45** (7/8/9) | .07 | 10 |
| *A full attention (P1)* | stuck-15 × 3 | *12/45* | *21/45* | *.06* | *16* |
| **B150 recency, hard 32K** | verified150, 8 agents | **77/150 (51%)** | **45/150 (30%)** | .051 | 29 |
| **C150 relevance, hard 32K** | verified150, 8 agents | **79/150 (53%)** | **45/150 (30%)** | .057 | 33 |

Fisher exact, two-sided: C150 vs B150 resolved p = 0.91, looped p = 1.0. Hard-cap C vs B (stuck-15) resolved p = 1.0, looped p = 0.40. Hard B vs A resolved p = 1.0. E-256K vs A looped p = 0.054; E-256K vs E-32K p = 0.48.

Verified150 ran at 8 agents in 70–76 min per arm (≈455 t/s aggregate, GPU 88%), grading included; engine peaks 38.4–38.7K.

## Conclusions

1. **zend's looping is an engine property, not a retention one.** 67–78% of tasks loop whether the window is 32K, 64K or 256K (holds the whole history); the window does nothing (256K vs 32K p = 0.48). Every vLLM arm on the same weights, from unconstrained full attention to a hard 32K cap, sits at 31–47%. Arm E therefore says nothing about provenance-selected retention; it says the zend build (its own quantisation, KV compression and sampling path) loops more than vLLM/AWQ on this model. H4 as posed cannot be tested until retention can be varied *within* zend with that held fixed.
2. **H2 is not supported.** At a true matched budget, relevance-selected retention does not beat recency: identical on n = 150 (79 vs 77 resolved, 45 vs 45 looped) and indistinguishable on the stuck-15 (14 vs 13, 24 vs 19). P1's directional "relevance ≥ recency" was measured on the blind ruler and does not replicate. *What* you keep — recency vs bge-small relevance, at least — does not matter here.
3. **How much you keep barely matters either, down to a third.** A hard 32K with past reasoning clipped first solves at least as many stuck-15 tasks as full attention (13–14 vs 12 of 45, n.s.) and loops no more. Combined with P1's A/B/C/D row, the retention *budget*, over the range 32K → unbounded, is not what drives either solves or looping for this agent on this model.
4. **The live hypothesis: the agent's own past reasoning in context.** The one thing the three good arms share is that the model sees almost none of its earlier thinking (hard mode clips it first; soft mode kept it and did no better with twice the context). An arm with a *soft* budget but `reasoning_content` stripped would isolate it in one run of six jobs. Proposed as the first P3 cell.
5. **Looping is the agent's, not the window's** (H1, still standing, now at n = 150): 30% of Verified tasks loop with a hard cap, 30% without a cap of consequence; the shape is canonical period-1 cycles (the same *kind* of action re-issued — 87–92 of 150 tasks) with free text drifting, which exact-match counting misses entirely (0/150).

## Caveats

- n = 45 for the stuck-15 cells; only the zend-vs-vLLM gap approaches significance there. n = 150 cells are the ones to quote.
- Hard mode changes two things at once (budget size and reasoning retained); conclusion 4 is the proposed disentangling, not a result.
- verified150 is one seed per arm (150 tasks each). Seed variance on 15-task cells was ±2 solves; on 150 it should be well under the 2-task difference observed, but a second seed would close it.
- The two B hard-cap sets differ only in the ruler; both are reported. The C old-ruler runs were superseded before running.
- Operational: Docker Hub's anonymous limit (100 pulls / 6 h / IP) stopped the first image pre-pull at exactly 100 of 150; a retry 6 h later completed it. The pre-pull now detaches so it never blocks the GPU queue.

## What's next (P3)

- **Reasoning-stripped soft arm** (6 jobs) — the disentangling run.
- **Second seed on verified150** for B and C (and A at full attention on Verified, as the ceiling there).
- Retention varied *inside* zend with engine fixed — only if the zend build's looping can be understood first; otherwise park arm E.
- The window × step-budget factorial (H3) can now be done on vLLM alone.

Runs: `agent-bench/runs/2026-11-01_*_p2-*` and `2026-11-0[12]_*_p2-*150*` on the box; job logs `queue/logs/20261101-20*_9[3-9]-*` through `20261102-0*_107-*`.
