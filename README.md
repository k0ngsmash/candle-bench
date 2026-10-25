# candle-bench

Reproducing and extending the measurements of
[john-sharratt/candle](https://github.com/john-sharratt/candle), a research fork of Hugging Face
Candle that serves LLMs over a three-tier (VRAM → RAM → NVMe) paged KV cache with per-block KV
compression, provenance-selected attention and MoE expert streaming.

The upstream repository publishes every claim as a `cargo test` gate and measures it on three
machines: an RTX 4090 Laptop (16 GB, PCIe 4.0 ×8), an RTX 3090 (24 GB, PCIe 3.0) and an RTX PRO
5000 Blackwell (72 GB). This repository runs the same gates on other hardware and keeps the
results in the upstream TSV format, so they can be compared row for row.

## Hosts

| Host | GPU | Link | CPU / RAM | Notes |
|---|---|---|---|---|
| [thor](hosts/thor.md) | RTX 4090 desktop, 24 GB, sm_89 | PCIe 4.0 ×16 | Ryzen 7 9800X3D, 64 GB DDR5 | Same chip as the upstream laptop with 1.5× the VRAM and 2× the link; same VRAM as the upstream 3090 on a newer architecture |

## Layout

```
ladder.csv            the gates, smallest first; `enabled` picks the default run
scripts/run-ladder    update to upstream main, build once, run each gate, file results
scripts/parse-gate    gate log -> upstream TSV columns
scripts/setup/        one-off Windows toolchain setup (CUDA 12.9.1 toolkit only, VS C++ tools, Rust)
results/index.tsv     one line per gate run: date, host, commit, exit code, rows, wall time
results/<date>_<host>_<commit>/   host.txt, <gate>.tsv, <gate>.log
notes/                learning log and open questions
```

## Running

Windows, NVIDIA driver installed, toolchain from `scripts/setup/`. Then:

```
scripts\run-ladder.cmd                          # every enabled gate
scripts\run-ladder.cmd -Only qwen3-30b-a3b      # one gate
```

Each gate runs as its own process with the card to itself, as upstream requires — close anything
else using the GPU first. In the TSVs, `prefill_tps` is the gate's `t/s (bulk)` column and
`decode_tps` is `t/s (single)`, both summed across concurrent sessions.

## Caveats

Results are tied to an upstream commit; the engine changes daily, so compare rows from the same
or nearby commits. Throughput on a desktop is affected by whatever else the machine is doing.
