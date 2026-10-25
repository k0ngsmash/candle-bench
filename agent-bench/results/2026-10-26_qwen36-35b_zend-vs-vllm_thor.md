# A coding agent on one RTX 4090: John's engine (zend) vs vLLM

**Machine:** thor — RTX 4090 desktop 24 GB, PCIe 4.0 ×16, Ryzen 7 9800X3D, 64 GB DDR5 @ 4800, Windows 11 + WSL2.
**Model:** Qwen3.6-35B-A3B at 4 bits — zend: `unsloth` UD-Q4_K_M GGUF (22 GB); vLLM 0.32.0: `cyankiwi` AWQ 4-bit (23.3 GB).
**Agent:** mini-swe-agent 2.4.6, unmodified, bash tool calls, step limit 75, same prompts for both.
**Tasks:** SWE-bench Lite test — every 10th instance (30, all 12 repositories); the 10-task sweeps use the first 10.
**Scoring:** the SWE-bench harness 5.0.2 (`SWE-bench/SWE-bench_Lite`), each fix run against the project's own tests.
**Sampling:** zend's hard-coded passthrough coding row (temperature 0.7, top-p 0.95, top-k 20, repetition penalty 1.05), given to vLLM as well.

zend runs from upstream `john-sharratt/candle` `35e9a2b8` with one local change, its prescribed model switched to
Qwen3.6-35B (`zend-qwen36.patch`), standalone, in passthrough mode. The model is 22 GB, so it does not fit beside a
working KV cache on 24 GB: zend streams experts through its three-tier cache; vLLM runs with `--cpu-offload-gb 6`
(16 GB of weights on the card), which on WSL2 needed `VLLM_WSL2_ENABLE_PIN_MEMORY=1`, a Linux CUDA toolkit and a
Linux-only `PATH`.

## Results

| Engine | Agents at once | Solved | Wall time | Minutes per task | Solved per hour | Generated t/s (all agents) | Per-call t/s (median) |
|---|--:|--:|--:|--:|--:|--:|--:|
| zend | 1 | 5 / 10 | 15.5 min | 1.6 | **19.4** | 133 | 143 |
| vLLM | 1 | 6 / 10 | 136.0 min | 13.6 | 2.6 | 17 | 16 |
| zend | 4 | 14 / 30 | 57.2 min | 1.9 | **14.7** | 116 | 26 |
| vLLM | 4 | 15 / 30 | 175.8 min | 5.9 | 5.1 | 44 | 12 |
| zend | 8 | 4 / 10 | 14.0 min | 1.4 | **17.1** | 150 | 21 |
| vLLM | 8 | 7 / 10 | 60.9 min | 6.1 | 6.9 | 44 | 10 |

Every run's folder under `agent-bench/runs/` holds its `summary.md`, the per-call log (`calls.jsonl`), GPU samples,
the predictions and the harness report.

## What it shows

1. **Throughput: zend does the same work 2.5–7× faster on this card.** Per hour it solved 3× as many tasks as vLLM
   at 4 agents, 2.5× at 8 and 7.5× at 1. vLLM's offload re-reads its 6 GB of offloaded weights over PCIe on every
   forward; zend keeps the experts in use resident.
2. **zend did not scale with concurrency here; vLLM did, up to a ceiling.** zend's aggregate generation stayed at
   116–150 t/s whether 1, 4 or 8 agents ran. Its log shows why: with one agent 97–100% of expert lookups hit VRAM;
   with four, the median hit rate fell to 79% (as low as 45%), because concurrent agents on different code route to
   more experts than the zone holds and each tool-output prefill concedes expert slots to its working buffers. vLLM went
   17 → 44 t/s from 1 to 4 agents (one weight read now serves several sequences) and stayed at 44 at 8, where the
   PCIe reads cap it.
3. **zend's history reuse works as designed.** The agents resent 28.1 M prompt tokens in the 4-agent run; zend
   prefilled 0.58 M of them (2%), matching the held history on 1,570 of 1,571 turns.
4. **Solve rates were close; zend's agents looped more.** Pooled over the three runs: zend 23/50, vLLM 28/50 — not a
   significant difference at this sample size (Fisher p = 0.42). But zend's agents ran out of steps 19 times in 50 against
   vLLM's 6 (p = 0.005), and produced more empty patches (13 vs 4 in the 30-task run). The exhausted trajectories repeat
   the same command many times (one ran an identical test script 27 times) with short reasoning. Candidate causes, not
   yet tested: zend keeps each turn's earlier reasoning in the context it attends to, where Qwen's own chat template
   drops past reasoning (which is what vLLM sees); zend's thinking-budget steering; the different 4-bit formats.

## Caveats

- One machine, one model, 50 task-runs per engine in all: solve-rate differences of a few tasks are noise.
- vLLM is at its worst here — offloading, under WSL2. On a card that holds the model it is a different engine; this
  measures what each engine does on a 24 GB card with this model, which is the question.
- The two engines load different 4-bit conversions of the same checkpoint.
- The step limit (75) is below mini-swe-agent's default (250) to bound run time; it affects both, but zend more.

## Next questions

- **Does a model that fits change the concurrency picture?** A 3-bit Qwen3.6-35B (~16 GB) on zend; Qwen3.5-9B on both.
- **Is the looping an engine behaviour?** Re-run zend's step-limit cases with past reasoning excluded from the context,
  and with the thinking budget off.
- **llama.cpp on the identical GGUF** as a third engine.
