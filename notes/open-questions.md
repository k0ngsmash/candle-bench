# Open questions

Things to understand, test, or raise upstream.

- **Model cache location.** `model_pack::cache_root()` is fixed to `%USERPROFILE%\.cache\zend\models`.
  A configurable root (a deployment path, which upstream's conventions allow) would help machines
  whose system drive is small. Candidate first PR.
- **Linux build.** INSTALL.md covers Windows only. Datacentre and cloud GPUs are mostly Linux.
- **Other architectures.** Kernels ship native code for sm_89 and sm_120. What happens on sm_90
  (H100/H200) and sm_100 (B200): PTX JIT, slower fallbacks, or validation failures?
- **Host link sensitivity.** How much do MoE gates gain from PCIe 4.0 ×16 over ×8 at the same
  VRAM? Compare thor with the upstream laptop on Qwen3-30B-A3B.
