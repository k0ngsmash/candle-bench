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
