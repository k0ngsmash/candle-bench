# Three-engine agent comparison: zend vs vLLM vs llama.cpp

thor (RTX 4090, 24 GB). Same model file (Qwen3.6-35B-A3B UD-Q4_K_M GGUF), same agent
(mini-swe-agent), same tasks (SWE-bench Lite subset), same sampling. zend loads its own
repacked copy of the GGUF; vLLM and llama.cpp load the file directly.

## Headline

1. **Looping is specific to zend.** On the 15 tasks zend got stuck on, zend repeats a command
   5+ times on 5-8 of 15 across every variant tried; llama.cpp on the identical file does so on
   1-2, vLLM on 1-3.
2. **Cause narrows to zend's context window.** zend projects each agent conversation through a
   32,768-token window, so an agent attends only to its newest ~32K tokens. Prompt size plateaus
   at ~32-35K on every zend task while the conversation keeps growing; on llama.cpp the same tasks
   grow to ~60K. Widening zend's window to 128K roughly halved looping at one agent - the only
   intervention that moved it.
3. **Ruled out as causes:** repetition penalty, reflection-word suppression, the thinking-token
   cap, sampling settings, the model file itself (llama.cpp on the same GGUF barely loops), KV
   compression (C0 near-lossless changed nothing), and agent notes (they live in the conversation,
   so they scroll out of the 32K view).
4. **Solve rates are comparable** across all three engines, within run-to-run noise.
5. **Speed and scaling differ sharply** (below).

## Looping (15 stuck tasks, 1 agent unless noted)

| Run | Solved | Hit step limit | Tasks looping (5+ repeats) |
|---|---|---|---|
| zend, standard | 1 | 11 | 8 |
| zend, control re-run | 4 | 11 | 5 |
| zend, reflection-penalty off | 1 | 14 | 7 |
| zend, KV compression C0 (x2) | 4 / 1 | 11 / 14 | 7 / 8 |
| zend, 128K window (x2) | 2 / 3 | 9 / 11 | 2 / 5 |
| zend, agent notes | 3 | 11 | 7 |
| llama.cpp (x3, incl. notes) | 3 / 4 / 5 | 7 / 7 / 6 | 1 / 2 / 1 |
| vLLM, penalty off (4 agents) | 5 | 5 | 3 |
| vLLM, default (4 agents) | 3 | 6 | 2 |
| vLLM, notes (4 agents) | 4 | 5 | 1 |

## Main run (30 tasks, 4 agents)

| Engine | Solved | Wall time |
|---|---|---|
| zend | 14/30 | 57 min |
| zend, 128K window | 10/30 | 116 min |
| vLLM | 15/30 | 176 min |
| llama.cpp | 17/30 | 70 min |

Widening zend's window cut looping but cost solves and doubled wall time at 4 agents on 24 GB:
longer histories compete with the streamed expert weights for memory.

## Concurrency (10 tasks)

| Engine | 1 agent | 8 agents | Aggregate gen. t/s (1 -> 8) |
|---|---|---|---|
| zend | 5/10, 15.5 min | 4/10, 14 min | ~133 -> ~150 (flat) |
| vLLM | 6/10, 136 min | 7/10, 61 min | ~17 -> ~44 (scales to PCIe cap) |
| llama.cpp | 6/10, 23.5 min | 6/10, 124 min | ~70 -> ~17 (degrades) |

- **zend** is 2-8x faster single-stream (~125-140 t/s per call) but does not scale with agents on
  24 GB - expert-cache hits fall under concurrency.
- **vLLM** is slowest single-stream (~16 t/s) but the only engine that goes faster with more agents,
  up to the PCIe offload cap.
- **llama.cpp** is mid single-stream (~72 t/s) and gets slower under concurrency: with experts
  offloaded to CPU (`--n-cpu-moe`), eight agents saturate the CPU path.

## Caveats

- One 24 GB consumer card, one model, a SWE-bench Lite subset. Figures are directional, not a
  leaderboard.
- 15-task runs swing by several solves between identical runs; looping is read as the robust
  signal, solve counts as noisy.
- Each engine was given its best-found offload setting for the card.
