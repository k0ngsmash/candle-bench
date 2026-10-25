# Learning log

## 2026-10-25

- Toolchain on Windows per upstream INSTALL.md: CUDA 12.9.1 toolkit only (12.4 cannot target
  sm_120, 13.x breaks cudarc), VS 2022 C++ Build Tools, Rust MSVC host.
- PowerShell 5.1 pitfalls met along the way: `Invoke-WebRequest` is too slow for multi-GB
  downloads (use `curl.exe`), and `Start-Process -Wait` hangs on the CUDA installer because it
  waits for every descendant process.
- First full build of the CUDA test binary: 9 min on the 9800X3D.
- Qwen2-0.5B smoke gate passes. Model packs are cached under `%USERPROFILE%\.cache\zend\models`
  regardless of `HF_HOME`; run-ladder links that folder to D:.
- First ladder at upstream `bdc60bd3` (RAM at 4800): Qwen2-0.5B, Llama-3.2-3B, Qwen3.5-0.8B,
  Qwen3-8B, Qwen3-30B-A3B — all validated rows pass. 30B gate takes ~13 min. See
  `results/2026-10-25_thor_bdc60bd3/comparison.md`.
- Qwen3.6-35B-A3B width + 32K/128K depth gates at `7f4033e1`: all pass. 8,650 of 10,496 expert
  slots fit in VRAM with a 97–100% hit rate, so the link was barely used. See
  `results/2026-10-25_thor_7f4033e1/comparison.md`.
