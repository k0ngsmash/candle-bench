# P4 — a second model family, and the first look at whether the cap ever bit

**Date:** 2–3 Nov 2026 · **Box:** same RTX PRO 6000 (96 GB) · **Engine:** vLLM 0.32.0 · **Agent:** mini-swe-agent 2.4.6, step limit 75 · **Grading:** SWE-bench harness

P1–P3 found no effect of context retention on Qwen3.6-35B-A3B. P4 asks whether that null is a property of the model. It also records the first re-slice of P1–P4 by how much history the cap *actually removed* (job 181, the opening step of P5), which changes how the null should be read.

## 1. gpt-oss-120b: unusable in this harness

gpt-oss-120b was the first choice for the second family. It could not be measured:

- 11–14 of 15 stuck-15 tasks ended in `RepeatedFormatError`, with Qwen's sampling and with gpt-oss's recommended sampling (temperature 1.0, top_p 1.0, no penalties).
- 98 of 101 format errors were malformed tool-call argument JSON; about 20% of all tool calls were malformed.
- A proxy-side repair (`harness/toolargs.py`) fixed **0 of 91** cases. The shapes were guessed rather than taken from the logs; the repair is kept, logged and off by default.

With most tasks ending in format failure, any retention arm would measure the tool-call parser, not the agent. gpt-oss is recorded as unusable here and was not pursued.

## 2. Devstral Small 2 (Mistral, 24B dense)

`mistralai/Devstral-Small-2-24B-Instruct-2512`, vLLM `mistral` tool parser, temperature 0.15 (model card). Format gate: **0 of 15** format errors. `mistral_common` had to be pinned to 1.12.0 (1.13 breaks vLLM 0.32); the setup script now pins it.

### stuck-15 (45 task-runs per cell)

| arm | resolved | looped (k=3) | canonical cycles |
|---|---|---|---|
| A full history | **8** (3/3/2) | 36 | 10 |
| B recency, hard 32K | **9** (2/3/4) | 27 | 14 |

Resolved p = 1.0; looped p = 0.065; cycles p = 0.48.

### verified150 (150 task-runs, 8 agents, one seed each)

| arm | resolved | looped | canonical cycles | hit step limit | engine peak med / max | wall |
|---|---|---|---|---|---|---|
| A full history | **65** (43%) | 101 | 44 | 61 | 30K / 58K | 184 min |
| B recency, hard 32K | **69** (46%) | 102 | 36 | 51 | 29K / 39K | 176 min |

Resolved p = 0.73; looped p = 1.0; cycles p = 0.36; step-limit exits p = 0.28. For comparison, Qwen's A150 resolved 74/150 (Devstral vs Qwen p = 0.35).

### What changes with the model, and what does not

- **Same null on retention.** Full history and a hard 32K cap are indistinguishable on both task sets, as on Qwen.
- **The two models loop in different shapes.** Devstral re-issues an exact command 3+ times in about 68% of Verified tasks (Qwen: ~33%), but falls into canonical cycles — the period-1 "same kind of action, drifting text" signature — less often (24–29%; Qwen A150: 57%). Devstral repeats verbatim; Qwen repeats with variations. Neither count alone is comparable across models.
- **Devstral runs out of steps far more often**: 61 of 150 under full history hit the 75-step limit (Qwen A150: 31). That is a large share of tasks stopped before they finish — the regime where history should matter is the one this setup cuts off.

## 3. Did the cap ever bite? (P5 step 1, `harness/dose.py`)

The run summaries showed the median capped task kept every turn ("kept 30 of 30"). Job 181 maps each proxy call back to its task and records, per task-run, the largest share of history the cap removed. Then, on the tasks where the cap bit, it compares the capped outcome against the **same tasks** under full history.

| cell | task-runs where cap bit | capped & bitten resolved | same tasks, full history |
|---|---|---|---|
| Qwen stuck-15, soft 32K recency (P1) | 4 / 45 (9%) | 0% | 0% |
| Qwen stuck-15, soft 32K relevance (P1) | 6 / 45 (13%) | 0% | 22% |
| Qwen stuck-15, compaction (P1) — ~95% removed | 13 / 45 (29%) | 8% | 33% |
| Qwen stuck-15, hard 32K recency (P2) | 16 / 45 (36%) | 6% | 25% |
| Qwen stuck-15, hard 32K relevance (P2) | 13 / 45 (29%) | 23% | 33% |
| Qwen verified150, hard 32K recency (2 seeds) | 62 / 300 (21%) | 8% | 10% |
| Qwen verified150, hard 32K relevance (2 seeds) | 73 / 300 (24%) | 12% | 26% |
| Devstral stuck-15, hard 32K recency | 8 / 45 (18%) | 0% | 12% |
| Devstral verified150, hard 32K recency | 17 / 150 (11%) | 29% | 18% |

What it shows:

1. **The cap bit in a minority of task-runs: 9–36%, and when it did it usually removed 10–25% of the history.** The soft caps of P1 were mostly no treatment at all. The headline nulls averaged a small effect over a mostly untreated population.
2. **The tasks the cap bites are the hard ones.** Qwen verified150: bitten tasks resolve 8–12% when capped, but un-bitten tasks resolve 60–64% — and the same bitten tasks resolve only 10–26% with full history. Long tasks are hard regardless. Any comparison that ignores this confounds task length with treatment.
3. **On the same tasks, removing history tends to cost solves — and more so as more is removed.** Pooling Qwen's four hard-cap cells: about 18 of 164 bitten task-runs resolved (11%) versus about 20% for the same tasks under full history. Removing 25–50% of the history: relevance 4% vs 30% (n = 27), recency 0% vs 0–14%. Compaction (≈95% removed): 8% vs 33%. Un-bitten tasks show no gap (60% vs 60%; 64% vs 57%), which is what a real effect predicts.
4. **This is suggestive, not established.** Cells are small (n = 4–73), the verified150 full-history reference is a single seed, and Devstral's verified cell goes the other way (29% vs 18%, n = 17). No test here is significant on its own.

**Reading P1–P4 again:** the null holds for short tasks, where the cap removes little or nothing, which is most of SWE-bench at a 75-step limit. It does *not* show that history is irrelevant. Where the cap removed real history, the signs point toward a cost. P5 tests this directly with caps that bite (8K and 16K) and step limits that let long tasks run (150 and 250).

## Caveats

- Devstral verified150 cells are single seeds; seed swing on Qwen was 3–6 solves.
- The dose analysis is observational within each arm: which tasks get bitten is decided by the task, not randomised. The same-task comparison controls for task difficulty, but not for the capped run's own path (a capped run that wanders gets longer and gets bitten more).
- Devstral and Qwen use different tool-call parsers and sampling; cross-model loop rates are not like-for-like.

Runs: `agent-bench/runs/*_p4e-*` on the box; job logs `queue/logs/20261102-*_17[1-9]-p4e-*`, `20261103-000409_179-p4e-B150hard.log`, `20261103-030005_181-dose-existing.log`.
