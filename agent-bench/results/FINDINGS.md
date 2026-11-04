# What a coding agent needs to remember — findings so far

*Consolidated from P1–P5 (1–4 Nov 2026). Status: P7 (firming up and locating the floor) is running; sections marked **[P7]** will be updated when it finishes. The per-phase write-ups in this folder are the detailed record; where they disagree with this page, this page is current.*

## The question

A coding agent works through a task one step at a time, and its history (every command, every output, every bit of its own reasoning) grows as it goes. Any real system has to cap that history somewhere. Does it matter **how much** you keep, and does it matter **what** you keep?

We also measured **looping**, an agent re-issuing actions it has already taken, because it is the failure most often named in the literature and almost never measured.

## The short answer

> An agent needs a **floor of memory** and **enough steps**. Above the floor, which parts of its history it keeps make no difference. Below it, the agent forgets what it did, redoes it, and goes round in circles, and more steps do not fix that.

| # | Finding | Confidence |
|---|---|---|
| 1 | **What you keep does not matter.** Keeping the most recent history and keeping the most relevant history (embedding retrieval) give the same results everywhere. | High |
| 2 | **Keeping too little hurts, and more steps do not fix it.** Cutting history to about a fifth (8K tokens) costs 10–13 points of solve rate; with more steps the agent loops more instead of recovering. | High |
| 3 | **The step limit was a hidden bottleneck.** At 75 steps many tasks were cut off before finishing; at 150, the full-history agent solves 92/150 instead of 74/150. | High |
| 4 | **Looping is the agent's own habit,** present in a third or more of tasks however much history it has. Starving it of history makes it worse. | High |
| 5 | **About half the history costs nothing,** if the agent has enough steps. | Medium: stuck-15 only **[P7]** |
| 6 | **Harder tasks suffer more from lost history,** once the step limit stops masking it. | Low–medium: one seed **[P7]** |
| 7 | **The zend engine loops far more than vLLM** on the same model, at every window size: a property of that engine build, not of its retention approach. | High |

## How we got here (and what we got wrong on the way)

The early rounds (P1–P4) compared retention strategies at a 32K cap with a 75-step limit and found **no differences**. That was first read as "context retention doesn't matter". It was wrong, for two reasons that only surfaced later:

1. **The cap rarely bit.** Most tasks finished, or hit the step limit, before their history outgrew 32K. Measured per task, the cap removed history in only 9–36% of runs, and usually only 10–25% of it. The comparisons were between near-identical runs. (P5, `harness/dose.py`.)
2. **The step limit cut off the long tasks**, which are exactly where history should matter. The full-history agent itself was being held back. (P5 follow-up.)

Two earlier corrections are also folded in:

- **The token ruler did not count the model's reasoning text**, so the early "32K" budgets were really ~60K. Fixed before P2; P1 comparisons were matched but mislabelled.
- **An early single-seed result** ("a wider window halves zend's looping") did not replicate across three seeds.

Hypotheses tested and rejected along the way: relevance beats recency at matched budget (H2, rejected at every budget); the agent's own past reasoning in context drives its failures (P3, rejected: stripping it changes nothing but saves 15–35% of tokens).

## The evidence

Model: Qwen3.6-35B-A3B (4-bit AWQ) on vLLM 0.32.0 unless stated. Agent: mini-swe-agent 2.4.6. Tasks: **verified150**, a stratified 150-task slice of SWE-bench Verified; **stuck-15**, 15 SWE-bench tasks the agent found hard. Graded with the SWE-bench harness. About 3,000 graded task-runs in all.

### Finding 1: what you keep does not matter

| setting | recency | relevance |
|---|---|---|
| verified150, hard 32K, 75 steps, 2 seeds | 148/300 | 155/300 (p = 0.62) |
| stuck-15, hard 16K, 75 steps | 10/45 | 13/45 |
| stuck-15, hard 16K, 150 steps | 18/45 | 19/45 |
| verified150, hard 8K, 75 + 150 steps | 128/300 | 138/300 (p = 0.46) |

Model-written compaction (P1) also matched recency (9 vs 9 of 45) while costing extra model calls.

### Finding 2: too little memory hurts, and steps do not rescue it

verified150:

| | 75 steps | 150 steps |
|---|---|---|
| full history | 74/150 | **92/150** |
| hard 8K (recency + relevance) | 123/300 (41%) | **143/300 (48%)** |
| *p, 8K vs full at 150 steps* | | *0.007* |
| step-limit exits, 8K | 117/300 | 86/300 (full history at 150: 2/150) |
| looped, 8K | 93/300 | 147/300 (full history at 150: 55/150, p = 0.016) |

At 8K the cap reaches 96–97% of tasks and removes ~75% of their history. On the same tasks, capped runs resolve 43–50% vs 61% with full history.

### Finding 3: the step limit

- Full history, verified150: 74 → 92 of 150 going from 75 to 150 steps (p = 0.048); step-limit exits 31 → 2.
- 16K cap, stuck-15: 23/90 → 62/150 going from 75 to 150–250 steps (p = 0.018). 250 steps adds nothing over 150.

### Finding 4: looping

- 31–47% of tasks loop (re-issue an action 3+ times) on vLLM at every retention setting, at 75 steps. The canonical shape is a **period-1 cycle**: the same *kind* of action re-issued with drifting text, which exact-match counting misses almost entirely.
- Cutting history does not change the rate at 75 steps, but at 150 steps an 8K-capped agent loops more than a full-history one (49% vs 37%).

### Finding 5: half the history is free, given steps **[P7]**

stuck-15, same step limit, full history vs hard 16K (which removes ~40–55% of history on the tasks it reaches):

| step limit | full history | 16K (recency + relevance) |
|---|---|---|
| 150 | 24/60 | 37/90 (p = 1.0) |
| 250 | 11/30 | 25/60 (p = 0.82) |

Full history at 250 steps peaks at 140–150K tokens; the 16K arms send ~16K. **[P7]** repeats this on verified150 and adds 12K to locate the floor.

### Finding 6: difficulty **[P7]**

verified150 at 150 steps, by SWE-bench Verified's human time-to-fix estimate:

| difficulty | tasks | full history | hard 8K (2 arms) | p |
|---|---|---|---|---|
| under 15 min | 66 | 68% | 60% | 0.28 |
| 15 min – 1 hour | 77 | 58% | 41% | **0.017** |
| 1–4 hours | 7 | 29% | 7% | – |

At 75 steps the same breakdown showed no pattern, because full history could not finish the medium tasks either (36%). The set has only 7 tasks in the hardest band, so it cannot test the hardest work.

### Finding 7: the engine

zend loops in 67–78% of stuck-15 tasks at 32K, 64K and 256K windows; vLLM on the same weights loops in 31–47%. The window size makes no difference inside zend, so this is the engine build (its own kernels and KV compression), not its retention policy.

### A second model family

- **Devstral Small 2** (Mistral, 24B dense) reproduces the 32K, 75-step null: full history 8/45 vs 9/45 on stuck-15, 65/150 vs 69/150 on verified150. Tight caps and longer step limits were not run on it.
- **gpt-oss-120b** could not be measured: 11–14 of 15 tasks ended in malformed tool calls.

## What this means

- **For building agents:** do not spend effort on clever retrieval over the agent's history; a plain recent window works as well. Size the window above the floor (16K was enough here, 8K was not), and give the agent a generous step budget. Fix looping in the agent itself (stuck detection, an explicit plan), because retention will not.
- **For the original premise:** the idea that smarter selection of what to keep is the lever for long-horizon agents is not supported. The lever is having enough memory at all; past that, selection is irrelevant.

## Open questions

1. **Where exactly the floor is.** Between 8K and 16K on these tasks; **[P7]** tests 12K. It is probably relative to task length, not a fixed number of tokens.
2. **Hard, long tasks.** This task set has almost none that the agent can solve. A multi-file, long-horizon set is needed to test whether history matters more on harder work.
3. **Other models at a tight cap.** Devstral was only tested at 32K and 75 steps.
4. **Fixing looping at the agent level**, which looks like the largest remaining practical gain.

## Tools built (all in `agent-bench/harness/`)

- `proxy.py` + `context_policy.py`: retention policies applied between agent and engine (recency, relevance via bge-small, compaction; soft or hard cap; reasoning stripping); per-call logging of what was removed.
- `loopmetrics.py`: looping and cycle detection (exact and canonical-shape), per-step reliability fit.
- `dose.py`: per-task measure of how much history the cap actually removed, with same-task comparison against a reference arm.
- `strata.py`: outcomes by task difficulty (SWE-bench Verified time-to-fix estimate, gold-patch files and lines).
- `cloud/run_bench_linux.py`: one-command runs on a single GPU box, with engine reuse; `runner/queue-runner.sh`: a gated, self-pausing job queue.

## Per-phase write-ups

P1 `2026-11-01_p1-retention-arms.md` · P2 `2026-11-02_p2-engine-hardcap-verified150.md` · P3 `2026-11-02_p3-reasoning-verified150.md` · P4 `2026-11-03_p4-second-family.md` · P5 and follow-up `2026-11-03_p5-dose-steps.md`
