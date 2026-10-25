# thor

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24 GB GDDR6X, compute capability 8.9 (Ada) |
| Link | PCIe 4.0 ×16 (measured `pcie.link.gen.current=4`, `width.current=16`) |
| Driver | 616.56 (WDDM; the card also drives the desktop) |
| CPU | AMD Ryzen 7 9800X3D, 8C/16T |
| RAM | 64 GB DDR5 (2×32 GB 6000 CL30 kit, running at 4800 MT/s — EXPO off) |
| NVMe | Samsung 980 PRO 1 TB (PCIe 4.0) |
| OS | Windows 11 |
| Toolchain | CUDA 12.9.1 (toolkit only), MSVC Build Tools 2022, Rust stable |

## Why it is a useful data point

- **vs the upstream RTX 4090 Laptop:** same sm_89 chip; 24 GB instead of 16 GB and ~25 GB/s
  host link instead of ~12 GB/s. Differences isolate VRAM capacity and link bandwidth, which
  matter most for MoE expert streaming.
- **vs the upstream RTX 3090:** same 24 GB; sm_89 has native FP8 and the BMMA provenance path
  that sm_86 lacks, and a link twice as fast.

## Changes to record if made

RAM speed (EXPO on/off) and anything else sharing the GPU change the results; note the date of
any change here and do not mix runs across it.
