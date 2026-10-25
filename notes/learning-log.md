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
