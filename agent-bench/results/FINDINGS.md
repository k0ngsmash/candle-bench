# What a coding agent needs to remember — findings

*Consolidated from P1–P7 (1–5 Nov 2026). The per-phase write-ups in this folder are the detailed record; where they disagree with this page, this page is current.*

## The question

A coding agent works through a task one step at a time, and its history (every command, every output, every bit of its own reasoning) grows as it goes. Any real system has to cap that history somewhere. Does it matter **how much** you keep, and does it matter **what** you keep?

We also measured **looping**, an agent re-issuing actions it has already taken, because it is the failure most often named in the literature and almost never measured.

## The short answer

> An agent needs a **floor of memory** and **enough steps**. Above the floor, which parts of its history it keeps make no difference. Below it, the agent forgets what it did, redoes it, and goes round in circles, and more steps do not fix that. On these tasks the floor lies between 8K and 12K tokens of history.

| # | Finding | Confidence |
|---|---|---|
| 1 | **What you keep does not matter.** Keeping the most recent history and keeping the most relevant history (embedding retrieval) give the same results everywhere. | High |
| 2 | **Keeping too little hurts, and more steps do not fix it.** At 8K tokens of history the agent solves ~10 points fewer tasks, runs out of steps far more often and loops more. | High |
| 3 | **There is a floor, between 8K and 12K.** 12K and 16K of history match full history on the main benchmark; 8K does not. | High (one benchmark, one model) |
| 4 | **The step limit was a hidden bottleneck.** At 75 steps many tasks were cut off before finishing, which masked the effects above. | High |
| 5 | **Below the floor, harder tasks suffer most.** The 8K cost falls on medium-difficulty tasks; easy ones are barely affected. Above the floor there is no cost at any difficulty. | Medium–high |
| 6 | **Looping is the agent's own habit,** present in a third or more of tasks however much history it has. Starving it of history makes it worse. | High |
| 7 | **The zend engine loops far more than vLLM** on the same model, at every window size: a property of that engine build, not of its retention approach. | High |

## How we got here (and what we got wrong on the way)

The early rounds (P1–P4) compared retention strategies at a 32K cap with a 75-step limit and found **no differences**. That was first read as "context retention doesn't matter". It was wrong, for two reasons that only surfaced later:

1. **The cap rarely bit.** Most tasks finished, or hit the step limit, before their history outgrew 32K. Measured per task, the cap removed history in only 9–36% of runs, and usually only 10–25% of it. The comparisons were between near-identical runs. (P5, `harness/dose.py`.)
2. **The step limit cut off the long tasks**, which are exactly where history should matter. (P5 follow-up.)

Other corrections folded in:

- **The token ruler did not count the model's reasoning text**, so the early "32K" budgets were really ~60K. Fixed before P2; P1 comparisons were matched but mislabelled.
- **An early single-seed result** ("a wider window halves zend's looping") did not replicate across three seeds.
- **Seed-to-seed noise on 150 tasks is larger than first assumed:** full history at 150 steps scored 92 and 82 on two seeds. The P5 follow-up's single-seed "74 → 92" overstated the step-limit gain for full history; pooled over two seeds it is 74 → 87 (p = 0.09). Conclusions below use pooled seeds wherever they exist.

Hypotheses tested and rejected along the way: relevance beats recency at matched budget (H2, rejected at every budget); the agent's own past reasoning in context drives its failures (P3, rejected: stripping it changes nothing but saves 15–35% of tokens).

## The evidence

Model: Qwen3.6-35B-A3B (4-bit AWQ) on vLLM 0.32.0 unless stated. Agent: mini-swe-agent 2.4.6. Tasks: **verified150**, a stratified 150-task slice of SWE-bench Verified; **stuck-15**, 15 SWE-bench tasks the agent found hard. Graded with the SWE-bench harness. About 4,000 graded task-runs in all.

### The main result: verified150 at a 150-step limit (P5 follow-up + P7)

| history kept | runs | resolved | hit step limit | looped | share of history removed (median, when the cap bit) |
|---|---|---|---|---|---|
| full history (peaks ~110K) | 2 | **174/300 (58%)** | 4/300 | 100/300 | – |
| 16K | 2 (recency, relevance) | **165/300 (55%)**, p = 0.51 | 34/300 | 109/300 | 45–49% |
| 12K | 2 (recency, relevance) | **173/300 (58%)**, p = 1.0 | 38/300 | 122/300 | 52–62% |
| 8K | 4 (2 seeds × recency, relevance) | **291/600 (49%)**, p = 0.007 | 166/600 | 274/600 (p = 0.0004) | 73–76% |

p values are against full history. 8K vs 12K: p = 0.011.

Paired on the same tasks, where the cap removed history: 16K resolves 46–51% vs 50–51% with full history; 12K 52–55% vs 53–55%; 8K 45–50% vs 57%.

### Finding 1: what you keep does not matter

| setting | recency | relevance |
|---|---|---|
| verified150, hard 32K, 75 steps, 2 seeds | 148/300 | 155/300 (p = 0.62) |
| verified150, 150 steps, 16K + 12K + 8K (all seeds) | 312/600 | 317/600 (p = 0.82) |
| stuck-15, hard 16K, 75 steps | 10/45 | 13/45 |
| stuck-15, hard 16K, 150 steps | 18/45 | 19/45 |

Model-written compaction (P1) also matched recency (9 vs 9 of 45) while costing extra model calls.

### Findings 2 and 3: the floor

- **Above it (12K, 16K):** solve rate matches full history, on the whole task set and on the same tasks. The agent needs somewhat more steps (11–13% of runs hit the 150 limit vs ~1%), and loops slightly more at 12K (41% vs 33%, p = 0.08), but finishes as often.
- **Below it (8K):** ~9 points fewer solves; 28% of runs hit the step limit; looping rises to 46%. Doubling the step limit from 75 to 150 recovers only part of the gap (8K: 41% → 49%), because the agent spends the extra steps redoing work it can no longer see.
- **Where it sits:** between 8K and 12K tokens of history on these tasks. It is probably relative to how much a task needs to keep in view, not a fixed number.

### Finding 4: the step limit

- 16K cap, stuck-15: 23/90 → 62/150 going from 75 to 150–250 steps (p = 0.018). 250 steps adds nothing over 150.
- Full history, verified150: step-limit exits fall from 31/150 at 75 steps to 4/300 at 150; solves 74/150 → 174/300 (p = 0.09).
- At 75 steps the 8K cost on solves looked like ~9 points and nothing else did; the masking ran both ways.

### Finding 5: difficulty

verified150 at 150 steps, by SWE-bench Verified's human time-to-fix estimate (full history: 2 seeds; caps: all runs):

| difficulty | tasks | full history | 16K | 12K | 8K |
|---|---|---|---|---|---|
| under 15 min | 66 | 65% | 63% | 67% | 63% |
| 15 min – 1 hour | 77 | 55% | 51% | 53% | **39%** (p = 0.002) |
| 1–4 hours | 7 | 29% | 29% | 29% | 14% |

Above the floor there is no cost in any band. Below it, the cost falls on medium-difficulty tasks. At 75 steps the same breakdown showed no pattern, because full history could not finish the medium tasks either (36%). The set has only 7 tasks in the hardest band, so it cannot test the hardest work.

### Finding 6: looping

- 31–47% of tasks loop (re-issue an action 3+ times) on vLLM at every retention setting, at 75 steps. The canonical shape is a **period-1 cycle**: the same *kind* of action re-issued with drifting text, which exact-match counting misses almost entirely.
- Given 150 steps, an agent below the floor loops markedly more (46% at 8K vs 33% with full history, p = 0.0004); above it, little or no more (36–41%).

### Finding 7: the engine

zend loops in 67–78% of stuck-15 tasks at 32K, 64K and 256K windows; vLLM on the same weights loops in 31–47%. The window size makes no difference inside zend, so this is the engine build (its own kernels and KV compression), not its retention policy.

### A second model family

- **Devstral Small 2** (Mistral, 24B dense) reproduces the 32K, 75-step null: full history 8/45 vs 9/45 on stuck-15, 65/150 vs 69/150 on verified150. Tight caps and longer step limits were not run on it.
- **gpt-oss-120b** could not be measured: 11–14 of 15 tasks ended in malformed tool calls.

## What this means

- **For building agents:** do not spend effort on clever retrieval over the agent's history; a plain recent window works as well. Size the window above the floor (12K was enough here, 8K was not; leave headroom), and give the agent a generous step budget. Fix looping in the agent itself (stuck detection, an explicit plan), because retention will not.
- **For serving:** the KV cache an agent needs scales with the window it is given, not with its full history. A 12–16K window needs roughly a tenth of the KV memory of full history (which peaked at ~110–150K here), so many more agents fit on one card.
- **For the original premise:** the idea that smarter selection of what to keep is the lever for long-horizon agents is not supported. The lever is having enough memory at all; past that, selection is irrelevant.

## Open questions

1. **Does the floor move with the model and the task?** One model (35B MoE, 4-bit) and one benchmark. The floor needs re-measuring on larger models and on longer, multi-file tasks.
2. **Hard, long tasks.** This task set has almost none that the agent can solve. A multi-file, long-horizon set is needed to test whether history matters more on the hardest work.
3. **Prefix-cache reuse.** A sliding window changes the start of the prompt every step, which defeats prefix caching; trimming in chunks may keep both the memory saving and cache reuse.
4. **Fixing looping at the agent level**, which looks like the largest remaining practical gain.

## Tools built (all in `agent-bench/harness/`)

- `proxy.py` + `context_policy.py`: retention policies applied between agent and engine (recency, relevance via bge-small, compaction; soft or hard cap; reasoning stripping); per-call logging of what was removed.
- `loopmetrics.py`: looping and cycle detection (exact and canonical-shape), per-step reliability fit.
- `dose.py`: per-task measure of how much history the cap actually removed, with same-task comparison against a reference arm.
- `strata.py`: outcomes by task difficulty (SWE-bench Verified time-to-fix estimate, gold-patch files and lines).
- `cloud/run_bench_linux.py`: one-command runs on a single GPU box, with engine reuse; `runner/queue-runner.sh`: a gated, self-pausing job queue.

## Per-phase write-ups

P1 `2026-11-01_p1-retention-arms.md` · P2 `2026-11-02_p2-engine-hardcap-verified150.md` · P3 `2026-11-02_p3-reasoning-verified150.md` · P4 `2026-11-03_p4-second-family.md` · P5 and follow-up `2026-11-03_p5-dose-steps.md` · P7: this page (runs `runs/2026-11-0[45]_*_p7-*`, analysis log `queue/logs/*_233-p7-analysis.log`)
