# zend window-at-headroom — RTX PRO 6000 (96 GB), phase 1

Nebius RTX PRO 6000 Blackwell (96 GB, Server edition), Ubuntu 24.04, CUDA 13. Same model
(Qwen3.6-35B-A3B UD-Q4_K_M), agent (mini-swe-agent), task set (SWE-bench Lite "stuck15"), and
sampling as the earlier 24 GB runs. zend built natively on Linux (six portability fixes). The 35B
is fully resident on 96 GB — no expert streaming — the regime the 24 GB card could not reach.

## Headline

Widening zend's passthrough projection window removes most of the looping AND lifts task
completion, with generation speed up and wall time down — none of the solve/latency penalty the
same change cost on the 24 GB card. That penalty was memory contention; headroom removes it.
Separately, zend's aggregate throughput now scales with concurrency (it was flat on 24 GB).

## T1 — window sweep (stuck15, 1 agent; GPU peak ~94.6 GB every run)

| Window | Looping (5+ of 15) | Submitted/15 | Context peak med / max | Gen t/s | Wall |
|---|---|---|---|---|---|
| 32K (baseline) | 6 | 3 | 32,919 / 34,333 | 105 | 33.5 min |
| 64K | 3 | 5 | 36,692 / 65,150 | 128 | 30 min |
| 128K | 3 | 5 | 35,176 / 57,700 | 123 | 28.5 min |
| 256K | 3 | 8 | 36,545 / 59,838 | 129 | 25 min |

- 32K reproduces the 24 GB 4090 baseline exactly (6/15 looping, context pinned at ~33K): the card
  is not the variable, the window is.
- Clearing 32K halves looping (6 -> 3) and holds there; completions climb 3 -> 5 -> 5 -> 8;
  generation speed rises and wall time falls.
- On the 24 GB card, 128K cut looping but cost solves and doubled wall time at 4 agents. That
  penalty is gone here — it was longer histories competing with streamed expert weights for VRAM.
- Context tops out ~58-65K on these tasks, so beyond ~64K the window stops being the binding
  constraint; the residual 3/15 loop for a non-window reason (open follow-up).

## T2 — concurrency (32K binary, 10 tasks)

| Agents | Aggregate gen t/s | Wall | Submitted/10 |
|---|---|---|---|
| 1 | 145 | 16.5 min | 6 |
| 8 | 295 | 6.5 min | 7 |

Aggregate throughput doubles from 1 to 8 agents (145 -> 295 t/s), against flat (~133 -> 150) on the
24 GB 4090. Full residency removes the concurrency ceiling: zend wave-batches across agents when
its experts are not being streamed.

## Verdict

The passthrough-retention fix is validated on target-class hardware: a wider projection window
removes most of the looping and raises completion, and on a headroom card it costs nothing in
speed or solves. zend also scales with concurrency once resident.

## Caveats

- One 96 GB card, one model, a 15-task looping subset + a 10-task concurrency set. Directional, not
  a leaderboard.
- Server-edition card (~1.6 TB/s vs ~1.8 on the Workstation edition); NVIDIA rates compute as
  equivalent, so figures transfer with a note on the ~10% bandwidth gap.
- Loop metric is read from the agent trajectories (no SWE-bench Docker scoring in these runs);
  "Submitted" is agent completion, not verified resolution.

## Flash-Next gate (T3): inconclusive — prerequisite missing

Flash-Next is not a downloadable checkpoint like the 35B: zend prepares its model pack locally from
Q8_0 source shards (Qwen3.8-Flash-Next-Q8_0-00001..00006.gguf) via the quantized_qwen38_moe
preparation step. Those shards were not staged on the box and the pack was never prepared, so zend
exited at the "Loading model" step before reaching the MoE live-table step — the point where the
24 GB card hit CUDA_ERROR_ALREADY_MAPPED. The ceiling-vs-bug question therefore remains open;
answering it needs the Flash-Next source pack staged and prepared on the 96 GB card first.
