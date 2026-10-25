# thor vs the upstream fleet — 2026-10-25

thor (RTX 4090 desktop, 24 GB, PCIe 4.0 ×16) at upstream `bdc60bd3`, against the most recent
upstream rows for the same gates:

- **4090 Laptop 16 GB** — `docs/results/performance_rtx_4090_mobile_16gb_rows_2026-10-10.tsv`
- **3090 24 GB** — `docs/results/performance_rtx_3090_24gb_rows_2026-10-05.tsv`

Every validated row on thor passed (✓); the Q4_x rows are unvalidated by design, as upstream.

**Caveat that dominates everything below:** the upstream rows are 2–3 weeks older than thor's
commit, and the engine changes daily. Some of the gap is engine improvement, not hardware. A clean
hardware comparison needs the same commit on every machine.

Figures are prefill / decode in tokens per second, summed across sessions.

## Qwen3-30B-A3B (MoE, ~17 GB weights)

| Row | thor | 4090 Laptop | 3090 |
|---|--:|--:|--:|
| BF16 ×1 | 9,087 / **135.0** | 1,807 / 26.7 | 3,620 / 56.4 |
| BF16 ×10 | 17,230 / **788.8** | 5,503 / 219.5 | 4,869 / 336.2 |
| Q8_0 ×20 (1.88×) | 17,225 / 362.9 | 6,139 / 299.6 | 4,829 / 344.2 |
| C10 ×2 (5.45×) | 14,825 / 160.3 | 3,063 / 130.0 | 4,551 / 93.3 |

The model fits in 24 GB but not in 16 GB, where experts stream over a ×8 link: single-session decode
is 5× the laptop's. Against the 3090, which also fits it, thor is 2.4× on single-session decode and
2.3× at ten sessions.

The Q8_0 ×20 row is the odd one out: thor's decode there (363) is below its own BF16 ×10 row (789)
and barely ahead of the other machines. Worth understanding before quoting any concurrency figure.

## Qwen3-8B (dense)

| Row | thor | 4090 Laptop | 3090 |
|---|--:|--:|--:|
| BF16 ×1 | 12,193 / 95.4 | 5,652 / 60.5 | 3,184 / 77.9 |
| BF16 ×4 | 13,434 / 360.2 | 6,562 / 231.1 | 2,759 / 244.5 |
| C8 ×10 (4.79×) | 13,111 / 578.7 | 6,437 / 308.4 | 2,321 / 376.6 |

## Llama-3.2-3B (dense)

| Row | thor | 4090 Laptop | 3090 |
|---|--:|--:|--:|
| BF16 ×4 | 27,269 / 745.6 | 14,299 / 490.5 | 6,300 / 501.4 |
| C8 ×10 (3.99×) | 27,417 / 839.4 | 14,240 / 688.7 | 5,349 / 745.8 |

## Qwen3.5-0.8B (hybrid)

| Row | thor | 4090 Laptop | 3090 |
|---|--:|--:|--:|
| BF16 ×16 | 91,188 / 2,698 | 47,556 / **2,935** | 19,671 / 2,435 |
| C8 ×32 (3.98×) | 89,013 / 3,977 | 46,057 / 3,811 | 19,614 / 3,571 |

On the smallest model, decode is roughly equal across all three machines, and the laptop is ahead
at ×16, while prefill on thor is ~2×. Small-model decode is limited by per-step overhead rather than
by the card, so a faster card does not help it.

## What this suggests

1. **Fitting the model in VRAM is the biggest single factor.** 16 GB → 24 GB turns Qwen3-30B-A3B
   from streamed to resident and multiplies decode several times over.
2. **Prefill scales with the card; small-model decode does not.**
3. **The link-bandwidth question is still open.** Qwen3-30B-A3B is resident on thor, so PCIe ×16
   vs ×8 was barely exercised. A model larger than 24 GB (Qwen3.6-35B-A3B, ~28 GB) is the test.
