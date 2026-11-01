# P1 — what you keep vs. how much you keep: five retention arms at a matched budget

**Date:** 2026-11-01 · **Box:** RTX PRO 6000 Blackwell Server (96 GB), 24 vCPU, Ubuntu 24.04 · **Model:** Qwen3.6-35B-A3B (AWQ-4bit on vLLM 0.32.0; zend's own build for arm E) · **Agent:** mini-swe-agent 2.4.6, 4 parallel agents, step limit 75 · **Tasks:** the stuck-15 (SWE-bench Lite instances that looped on the 4090) · **Seeds:** 3 per arm · **Grading:** SWE-bench harness (resolved = tests pass), not "submitted"

The question: for a long-horizon coding agent, does *what* you keep in context matter more than *how much*? Five arms, same model, hardware, harness, tasks and sampling; arms B–D spend the same 32,768-token budget measured with one ruler (tiktoken cl100k), applied in the proxy with the engine untouched.

| Arm | Retention | Where |
|---|---|---|
| A | full attention, nothing evicted (`--max-model-len 131072`) | — (ceiling) |
| B | recency: task + last 4 turns + older turns newest-first to budget | proxy |
| C | relevance: task + last 4 turns + older turns ranked by bge-small cosine to the current step | proxy |
| D | compaction: task + a running model-written summary + last 4 turns | proxy (summary side-calls to the same engine) |
| E | zend, 32K projection window (provenance-selected KV retention) | engine |

## Results

Per arm, 15 tasks × 3 seeds = 45 task-runs. *Looped* = some command issued ≥3 times in a task (`loop_onset_3`); *rf* = share of actions that re-issue an earlier one; *LE* = agent hit the 75-step limit.

| Arm | Resolved (s1/s2/s3) | **Resolved /45** | Looped (s1/s2/s3) | **Looped /45** | rf | LE /45 | peak ctx median / max |
|---|---|---|---|---|---|---|---|
| A full attention | 5 / 4 / 3 | **12 (27%)** | 7 / 8 / 6 | **21 (47%)** | .064 | 16 | 33–42K / 73–79K |
| B recency 32K | 3 / 3 / 3 | **9 (20%)** | 8 / 6 / 5 | **19 (42%)** | .056 | 12 | 33–38K / 53–60K |
| C relevance 32K | 3 / 5 / 4 | **12 (27%)** | 4 / 7 / 3 | **14 (31%)** | .061 | 8 | 30–43K / 56–65K |
| D compaction 32K | 2 / 4 / 3 | **9 (20%)** | 4 / 4 / 7 | **15 (33%)** | .068 | 17 | 32–40K / 60–61K |
| E zend 32K window | 2 / 2 / 2 | **6 (13%)** | 14 / 9 / 12 | **35 (78%)** | **.182** | **35** | 33K / 35K (pinned) |

Per-step reliability (geometric fit, observed-steps variant): A .971–.981, B .967–.973, C .972–.980, D .961–.973, E .966–.970.

**Significance (Fisher exact, two-sided, 45 vs 45).** Looping: E vs A p = 0.004, E vs B p = 0.001. Every other pairwise difference — including every difference in *resolved* — is not significant at this n (C vs A looping p = 0.19; B vs A resolved p = 0.62). One finding is solid; the rest are directions to test at larger n.

## What it says

1. **Looping is not an overflow symptom.** The ceiling arm — the agent sees its entire history — still re-issues some command three times in 47% of tasks. Trimming to a 32K budget (B, C, D) did not increase looping; two of the three trimmed arms looped *less*. Whatever drives the cycling, "the window cut it off" is not the main story. (H1 supported in direction.)
2. **A hard 32K window is a different animal from a soft 32K budget.** zend's projection window pins the model's view at 32K; the proxy arms cap what is *sent* but never clip the last four turns, so their peaks reach 53–65K. Arm E, effectively given the least context of anyone, looped in 78% of tasks with 3× the repeat fraction and hit the step limit 35 times out of 45. This reproduces the 4090-era looping on the 96 GB card and is the only significant effect in the matrix. It is **not** a like-for-like test of engine-level vs application-level retention (H4) — that needs zend at a 64K window against the soft-32K arms, queued as the P1 extension.
3. **Relevance ≥ recency, directionally.** At the identical budget, C matched full attention on solves (12/45) where B did not (9/45), looped least of any arm (14/45) and hit the step limit least (8/45). None of it reaches significance at n = 45; it is the result to replicate at n ≈ 150 before claiming H2.
4. **Compaction is the expensive arm.** D sat with B on solves (9/45), middling on looping, and paid for it: 42–121 summary side-calls per seed, 500–1,500 s of extra model time and 55–165K generated tokens per run, plus the most empty patches. The industry's default fix was neither the best nor the cheapest here.
5. **The old yardstick under-counted.** The legacy "a command issued 5+ times" measure reports 0–2 tasks per run in arm A; `loop_onset_3` reports 6–8 on the same trajectories. Longest consecutive run is 1 in every single cell — the looping is a *cycle* (edit → test → same edit → same test), never a stutter. Any metric that only looks for consecutive repeats will miss it.

## Caveats, honestly

- **n = 15 tasks × 3 seeds.** Seed-to-seed swing is ±1–2 solves. Only arm E's looping clears significance. Directions 3–4 are hypotheses for P2, not findings.
- **Soft vs hard budget.** B/C/D never clip the last four turns (by design: the agent always sees its latest observations whole), so single calls can exceed the budget and one task in C3 hit vLLM's 64K ceiling (`ContextWindowExceededError`). zend's window is hard. The budgets are matched across B/C/D, not between them and E.
- **Ruler offset.** The proxy budgets in tiktoken cl100k tokens; vLLM reports Qwen tokens, ~17% more. "32K budget" is ~38K in the engine's count. Identical across B/C/D; recorded per run in `summary.json` (`policy.ruler`).
- **Stuck-15 is a hostile sample** chosen *because* it looped on the 4090. Absolute solve rates (13–27%) are not representative of SWE-bench Lite; the between-arm comparison is the point.
- **Harness noise.** `RepeatedFormatError` (malformed tool call) appeared once; the zend arm's 4-agent runs used `--seed` but zend may not honour it. Per-step reliability uses observed steps, not the agent-rot paper's intrinsic horizon — comparable in form, not in value.
- **Engine reuse** kept one vLLM instance across all of B and C and both D seeds (identical signature); the engine was restarted only at A→B (max-model-len) and D→E (engine). Reuse did not change any run's config.

## What's next (P1-ext / P2)

- **zend at a 64K window, 3 seeds** — the fair H4 cell. Phase 1 (single agent, ungraded) already showed 64K cutting zend's looping in half.
- **Replicate C vs B at n ≈ 150** (SWE-Verified slice) before claiming H2.
- **Clip the recent window too** (or raise `max-model-len` for the budget arms) so the soft cap becomes a real cap.
- **Period detection** in the loop metric: the cycles have period 2–4; `longest_run` is blind to them by construction.
- The window × step-budget factorial for H3.

Runs: `agent-bench/runs/2026-11-01_*_p1-arm*` on the box (`summary.json`, `summary.md`, `loop.csv`, `calls.jsonl`, trajectories). Job logs: `agent-bench/queue/logs/20261101-*_7[0-9]-p1-*` through `84`, re-summarized by `86`.
