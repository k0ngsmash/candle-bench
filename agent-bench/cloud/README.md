# Phase 1 on target infra — RTX PRO 6000 (96 GB)

Turn-key kit to run the phase-1 tests from the test plan on a rented Blackwell card: **T1 window-at-headroom** (the headline — does widening the projection window kill the looping once the model is fully resident and not fighting the expert cache for VRAM), **T2 residency & concurrency**, and **T3 the Flash-Next gate**.

These scripts are written against the harness and build recipe that are proven on thor, but they have **not been run on a cloud box** — so step 4 is a 2-task smoke that shakes out any port issue for pennies before the real runs. Treat the smoke as the gate.

## The box

- **1× RTX PRO 6000 Blackwell, 96 GB**, Ubuntu 24.04, a recent NVIDIA driver, CUDA 13 (most GPU images ship `nvcc`).
- **≥ 300 GB disk.** The 35B GGUF (~20 GB), the vLLM AWQ copy (~25 GB), four zend build trees, and — if you score solves — the SWE-bench Lite Docker images (tens of GB) all land here.
- Cheapest sensible hosts: **Vast.ai (~$1.64/GPU-hr)** or **Nebius (~$1.80)**, Workstation/Max-Q edition. Any provider is fine; the kit assumes only Ubuntu + the driver.
- Renting and paying for the box is your step — nothing here provisions or bills an instance.

## Run order

Clone this repo (candle-bench) onto the box, then from `agent-bench/cloud/`:

```bash
sudo bash 00-provision.sh     # Docker, NVIDIA container toolkit, build deps, Rust, uv  (once)
#   log out/in so the docker group applies
bash 01-setup-bench.sh        # vLLM + agent venvs, llama.cpp, model downloads            (~30–60 min)
bash 03-build-windows.sh      # builds zend at 32K/64K/128K/256K windows                   (~2 h)
bash 04-run-phase1.sh         # smoke → T1 window sweep → T2 concurrency
bash 05-t3-flashnext.sh       # T3: the Flash-Next ALREADY_MAPPED gate
```

Scoring (solves) is **off by default** — the loop metric, which is the headline, comes from the agent trajectories, not from Docker scoring. Once `01-setup-bench.sh` has confirmed Docker + the eval image work, add solves with:

```bash
EVAL=1 bash 04-run-phase1.sh
```

Everything the build takes — base commit, fork URL, model — is an env override at the top of `02-build-zend.sh`. Default base is the verified commit `35e9a2b8` with the six portability patches applied; once the Linux PR merges upstream you can bump `BASE` and drop the patches.

## What each test answers

| Test | Runs | Reads | Success |
|---|---|---|---|
| **T1** window sweep | zend at 32K/64K/128K/256K, stuck15, 1 agent | loop metric + context peak + solves | a window that drops looping to ≤2/15 **without** losing solves or doubling wall time — the fix works once memory contention is gone |
| **T2** concurrency | zend 32K, 10 tasks, 1 then 8 agents | aggregate gen t/s, solves | aggregate throughput rises with agents (vs flat on the 4090) — confirms the ceiling was expert-streaming |
| **T3** Flash-Next gate | stock Flash-Next, 2 tasks | does it serve; `zend.out` | clean serve ⇒ the 4090 failure was the 24 GB ceiling; repeat `ALREADY_MAPPED` ⇒ a real bug, capture operands with `tensor-assert` |

Results land in `agent-bench/runs/<date>_<label>_zend_w<N>/` with a `summary.md` per run — the `Looping:` line and the context-peak figures slot straight into `results/`. Sync the summaries back (the `.gitignore` keeps full trajectories local) the same way the thor runs do.

## Notes & caveats

- **No NVLink** on this card — relevant for the later 2-card 200B test, not for phase 1 (single card).
- **Edition.** Workstation/Max-Q hosts are ~1.8 TB/s, hyperscaler Server edition ~1.6 TB/s; compute is equivalent, but note which produced any absolute throughput number.
- **zend's model** is fetched on first launch into `~/hf-cache` (HF_HOME) — the first `04`/smoke run includes that download.
- **Cost:** phase 1 is a few hours of a ~$1.80/hr card plus ~2 h of builds — order of **$15–25** of compute; the real cost is setup and download time.
- Tear the box down between phases to stop the meter; the repo + results are all that need to persist.

## Retention arms (P1 of the research plan)

The question for the next box is *what you keep vs. how much you keep*: at a matched context budget,
does relevance-selected retention beat recency, and does either beat the field's default fix
(compaction)? The arms are context policies applied in `harness/proxy.py` — the engine is untouched,
only the message list it is sent changes. Definitions in `harness/context_policy.py`.

| Arm | Flag | What the engine sees |
|---|---|---|
| A full attention | `--policy none` | the whole history (vLLM at a large `--max-model-len`) |
| B recency | `--policy recency --budget-tokens N` | task + last K turns + older turns newest-first until N |
| C simple relevance | `--policy relevance --budget-tokens N [--embed-model bow\|BAAI/bge-small-en-v1.5]` | task + last K turns + older turns ranked by similarity to the current step until N |
| D compaction | `--policy compaction --budget-tokens N` | task + a running model-written summary + last K turns |
| E zend | `--backend zend` (window-built binary) | zend's own provenance-selected KV retention |

All budget arms use the same token counter (tiktoken cl100k, an approximation of the Qwen tokenizer;
the point is one ruler for every arm). A *turn* = one assistant tool call + its result; turns are kept
or dropped whole so the chat format stays valid. Retrieved history turns are clipped head+tail at
`--max-turn-tokens` (default 1024); the last-K window is never clipped. `--seed` fixes sampling per
repetition. Per-call policy stats (turns kept, tokens before/after) go to `calls.jsonl`; summaries
roll up into `summary.md`.

Example — arm C at a 32K budget, graded, seed 1:

    ZEND_WS=~/zend-ws HF_HOME=~/hf-cache ~/venvs/agent/bin/python run_bench_linux.py \
      --backend vllm --max-model-len 65536 --policy relevance --budget-tokens 32768 \
      --embed-model BAAI/bge-small-en-v1.5 --tasks-file ../stuck15.txt --workers 1 --seed 1 --label p1-armC

(`uv pip install tiktoken sentence-transformers` into the agent venv first; `--embed-model bow` needs nothing.)

### The loop metric

`harness/loopmetrics.py` defines looping precisely (an *action* = one normalised bash command):
`max_repeat`, `repeat_fraction`, `longest_run`, `loop_onset_k` (step at which some action is issued
for the k-th time; k=3 headline) and the legacy `looped_5plus`. Per-task rows land in `loop.csv`; the
run summary carries the aggregate and, when graded, a per-step reliability `r` fitted to
P(success | h steps) = r^h — the observed-steps variant of the agent-rot model, a secondary number.
`python harness/loopmetrics.py runs/<dir> ...` re-analyses any run. Early observation from the 4090
trajectories: the looping is a **cycle**, not a stutter — longest consecutive run 1–2, but the same
command re-issued 6–8 times across a 75-step run, onset around step 50–68.

Offline tests (no GPU): `python harness/test_context_policy.py [run_dir ...]`.
