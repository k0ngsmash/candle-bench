# P5 — when the cap actually bites, and when the agent has room to finish

**Date:** 3 Nov 2026 (03:00–16:40 SGT, unattended) · **Box:** same RTX PRO 6000 (96 GB) · **Model:** Qwen3.6-35B-A3B AWQ-4bit on vLLM 0.32.0 · **Agent:** mini-swe-agent 2.4.6 · **Grading:** SWE-bench harness

P1–P4 found no effect of context retention, but job 181 showed why that null was weak: at a 32K cap, with a 75-step limit, the cap removed history in only 9–36% of task-runs, and usually only 10–25% of it. Most tasks finish, or hit the step limit, before their history outgrows the cap. P5 asks the question again with a treatment that is actually applied:

1. **Tighter caps:** hard 8K and 16K, recency and relevance, stuck-15 × 3 seeds (75 steps), plus verified150 at 8K.
2. **Longer horizons:** step limits of 150 and 250 at 16K, with **full-history references at the same step limits**.
3. **Paired analysis** (`harness/dose.py`): for every task the cap actually reached, compare against the same task under full history.
4. **By difficulty** (`harness/strata.py`): SWE-bench Verified's human time-to-fix estimate and gold-patch size, which are independent of our agent.

## 1. Tighter caps, 75 steps

| cell | resolved | hit step limit | history removed (median, when bitten) | cap bit |
|---|---|---|---|---|
| full history (P1 A, stuck-15) | 12/45 | 16/45 | – | – |
| hard 32K recency (P2) | 13/45 | – | 18% | 36% |
| hard 16K recency | 10/45 (5/2/3) | 15/45 | 42% | 87% |
| hard 16K relevance | 13/45 (5/3/5) | 13/45 | 50% | 87% |
| hard 8K recency | 7/45 (1/3/3) | – | 79% | 98% |
| hard 8K relevance | 8/45 (3/2/3) | 26/45 | 82% | 100% |

On the same tasks, 8K-capped runs resolve 16–18% vs 27% with full history. Pooled 8K vs pooled 32K on stuck-15: 15/90 vs 27/90, p = 0.05.

### verified150 at 8K (one seed per arm)

| arm | resolved | hit step limit | looped |
|---|---|---|---|
| full history (P3 A150) | 74/150 | 31 | 49 |
| hard 32K, B + C, 2 seeds each (P2/P3) | 303/600 (50.5%) | – | – |
| **hard 8K recency** | **61/150** | **62** | 45 |
| **hard 8K relevance** | **62/150** | **55** | 48 |

- **8K pooled vs 32K pooled: 123/300 (41%) vs 303/600 (50.5%), p = 0.007.** The first significant effect of retention on solves in the program.
- **Step-limit exits: 117/300 vs 31/150 with full history, p = 0.0001.**
- **Looping does not change** (30–32% vs 33%).
- Paired: the cap reached 96–97% of task-runs and removed ~73% of the history; those tasks resolve 40% capped vs 48–49% with full history.

**Mechanism:** with most of its history gone, the agent does not loop more. It redoes work it can no longer see, and runs out of steps.

## 2. Longer horizons: full history vs 16K at the same step limit

| step limit | full history | hard 16K recency | hard 16K relevance | p (full vs 16K pooled) |
|---|---|---|---|---|
| 75 | 12/45 (P1) | 10/45 | 13/45 | – |
| 150 | **24/60** (7/6/5/6) | **18/45** (6/6/6) | **19/45** (7/6/6) | 1.0 |
| 250 | **11/30** (5/6) | **13/30** (7/6) | **12/30** (5/7) | 0.82 |

Paired, on tasks where the 16K cap removed history (~40–55% of it):

| | capped | same tasks, full history |
|---|---|---|
| 150 steps, recency | 28% (n = 36) | 26% |
| 150 steps, relevance | 40% (n = 42) | 36% |
| 250 steps, recency | 37% (n = 27) | 33% |
| 250 steps, relevance | 36% (n = 28) | 36% |

- **Given room to finish, removing half the history costs nothing.** At 150 and 250 steps, capped and full-history runs are indistinguishable on outcomes, on looping (55–64% both ways) and on the paired comparison.
- **The step limit was the binding constraint.** At 16K, 75 → 150+ steps: 23/90 → 62/150 (p = 0.018). Step-limit exits fall from ~30% to 3–10%. 150 and 250 steps give the same rate: these tasks finish by 150.
- **Full history at 250 steps peaks at 139–151K tokens**; the 16K arms send ~16K. The same outcome with roughly a tenth of the context.

## 3. By task difficulty

verified150, full history vs caps, resolve rate per SWE-bench Verified time-to-fix bucket:

| difficulty | tasks | full history | 32K recency / relevance (2 seeds) | 8K recency | 8K relevance |
|---|---|---|---|---|---|
| < 15 min | 66 | 70% | 61% / 67% | 59% | 56% |
| 15 min – 1 h | 77 | 36% | 41% / 40% | 27% | 31% |
| 1–4 h | 7 | 0% | 29% / 36% | 14% | 14% |

- **Difficulty dominates everything.** Full history solves 70% → 36% → 0% down the buckets. Harder tasks are where the cap bites, and where the agent hits the step limit (at 8K: 24–27% → 45–49% → 57–86%).
- **The cost of a cap does not grow with difficulty.** At 32K there is no consistent cost in any bucket. At 8K the cost is a roughly flat 5–14 points across easy and medium tasks. No per-bucket difference is significant.
- **The hardest bucket cannot answer the question:** full history solves 0 of 7, so there are no solves for a cap to take away. This task set has almost no tasks that are hard *and* solvable, which is where history should matter most.

## Conclusions

1. **The earlier null was mostly a weak treatment.** At 32K and 75 steps the cap rarely removed anything. With a treatment that bites, there is an effect.
2. **How much you keep matters at the extreme; what you keep does not.** Removing ~75–80% of history (8K) costs ~9 points of solve rate on Verified (p = 0.007). Removing ~50% (16K) costs nothing measurable once the agent has room to finish. Recency and relevance are level everywhere (P2–P5), so H2 stays rejected.
3. **The cost of losing history is spent as steps, not as loops.** A heavily capped agent redoes work it can no longer see. Step-limit exits double (p = 0.0001) while looping is unchanged. This is the agent-rot paper's per-step decay seen from the context side: less history, more steps per unit of progress.
4. **Step budget and history budget trade off.** At 75 steps, a 16K cap looks harmful only because the agent is cut off; at 150–250 steps it matches full history with a tenth of the context. Whether more steps also rescue an 8K cap is untested.
5. **Looping is a property of the agent and model, not of retention.** Its rate is unchanged across every cap and step limit tested.
6. **Nothing here shows history mattering more on harder tasks**, but this task set cannot test that: its hard tasks are unsolved either way.

## Caveats

- One model (Qwen3.6-35B-A3B), one agent harness, Python repository fixes. Devstral reproduced the 32K null (P4); P5 was not repeated on it.
- Stuck-15 cells are 45 task-runs (60 for full history at 150 steps): enough for a ~25-point effect, not a 10-point one. The Verified 8K arms are single seeds, and the full-history Verified reference (A150) is one seed.
- The paired comparison is observational within each arm. Which tasks get capped is decided by the task, and a capped run that wanders gets longer and is capped more.
- Only 5 of the stuck-15 tasks are in Verified, so stuck-15 difficulty buckets have 1–3 tasks each and are not interpreted.
- Run accounting: jobs 185 and 197 failed at start-up (proxy not yet listening on a reused engine) and were rerun after the fix in `f9aa869`; their empty run directories are matched by the analysis globs but contribute no task-runs. Job 208 lost its SSH session after the run had finished and been scored; its rerun (208r) was kept as a fourth seed.

Runs: `agent-bench/runs/2026-11-0[23]_*_p5-*` on the box. Job logs: `queue/logs/20261103-*_1[89][0-9]*-p5-*`, `*_20[0-9]*-p5-*`, `*_181-dose-existing.log`, `*_215-strata-early.log`, `*_217-dose-final.log`.
