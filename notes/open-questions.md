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
- **Same-commit comparison.** thor's rows are at `bdc60bd3`; upstream's latest laptop and 3090 rows
  are from 10-05 and 10-10. Separating hardware from engine improvement needs one commit run on
  every machine.
- **Qwen3-30B-A3B Q8_0 ×20 on thor.** Decode 363 t/s, below its own BF16 ×10 row (789). Is the
  Q8_0 KV read path or the 20-session admission the limit?
- **Stale depth table?** Upstream §3.2 (RTX PRO 5000) shows Qwen3.6-35B BF16 prefill 1,693 / 443 at
  32K / 128K; thor at `7f4033e1` measures 7,122 / 2,636. Worth asking whether a re-run on the
  reference card would refresh it.
- **Testing the link for real.** Qwen3.6-35B is 82% resident on 24 GB (hit 97–100%), so it barely
  uses PCIe. Flash-Next (180B) is the model that streams on 24 GB — but its 24 GB artifact is built
  from ~190 GB of Q8_0 shards, so it needs the disk and an overnight download.
