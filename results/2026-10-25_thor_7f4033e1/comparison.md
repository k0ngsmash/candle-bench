# Qwen3.6-35B-A3B on thor — 2026-10-25

thor (RTX 4090 desktop, 24 GB, PCIe 4.0 ×16, RAM at 4800) at upstream `7f4033e1`. Both gates pass,
every validated row ✓.

Upstream comparisons:
- **4090 Laptop 16 GB** — `performance_rtx_4090_mobile_16gb_rows_2026-10-10.tsv`
- **3090 24 GB** — `performance_rtx_3090_24gb_rows_2026-10-05.tsv`
- **RTX PRO 5000 72 GB** — `docs/performance.md` §3.2 (the only upstream depth sweep)

The upstream rows are 2–7 weeks older than thor's commit. Treat gaps as hardware *plus* engine change.

## Width gate (~700-token prompts)

| Row | thor | 4090 Laptop | 3090 |
|---|--:|--:|--:|
| BF16 ×1 | 2,182 / **287.1** | 439 / 71.6 | 953 / 38.1 |
| BF16 ×4 | 10,675 / 1,004.4 | 2,081 / 302.1 | 3,801 / 334.4 |
| C5 ×8 (3.91×) | 10,892 / 1,647.1 | 2,194 / 307.1 | 4,311 / 535.0 |
| C10 ×16 (6.42×) | 11,752 / **1,975.9** | 2,466 / 336.7 | 2,403 / 639.2 |

(Upstream's later 3090 sweep, 2026-10-10 at `c375834c8`, reports C10 ×16 at 1,346.3 decode.)

### Where the experts lived

The 22 GB checkpoint does not fit beside the KV cache and working buffers, so it ran through the
expert cache — but only just:

- **8,650 of 10,496 expert slots resident in VRAM** (18.1 GB of experts), the rest pinned in RAM.
- **Hit rate 96.7% on the first row, 99.7–100% on every later row.** Cold (NVMe) misses: zero.
- Host RAM held ~23 GB resident for the warm tier.

So on a 24 GB card this model is nearly resident, and the PCIe link and RAM speed are barely
exercised. **This run does not answer the link-bandwidth question, and a RAM-speed A/B on this
model would likely show little.** The laptop (16 GB) is where this model streams in earnest.

## Depth gate (one session, `Coherence`, 64 generated tokens)

| Mode | Prefill 32K | Prefill 128K | Decode 32K | Decode 128K | Compress 128K |
|---|--:|--:|--:|--:|--:|
| **thor** BF16 | 7,121.7 | 2,635.8 | 99.6 | 60.6 | — |
| **thor** C10 | 7,121.6 | 2,625.9 | 81.4 | 28.6 | 6.80× |
| PRO 5000 BF16 | 1,692.8 | 443.4 | 56.8 | 27.9 | — |
| PRO 5000 C10 | 1,637.4 | 456.4 | 41.4 | 14.5 | 7.17× |

Kept from 32K to 128K (BF16): thor **37% of prefill, 61% of decode**; upstream 26% / 49%.

thor's prefill at depth is ~4–6× upstream's 72 GB Blackwell figure. A desktop 4090 should not beat
that card by this margin on hardware alone, so this mostly measures how far the engine has moved
since upstream's depth table was recorded — **the published depth table looks stale.**

C10 halves decode at 128K on both machines (28.6 vs 60.6 here; 14.5 vs 27.9 upstream): compressed
KV reads cost more per token as the cache grows, which upstream's §3.5 already describes.

## What it means for long agent sessions

- A single agent with 128K tokens of memory on this model decodes at ~60 t/s uncompressed.
- Compression to ~7× buys memory capacity at the cost of half the decode at that depth.
- At short prompts, one 24 GB card sustains ~2,000 t/s aggregate across 16 sessions with 6.4× KV
  compression.
