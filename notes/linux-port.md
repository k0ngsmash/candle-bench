# Linux port of zend (candle-kernels)

The candle fork builds and runs on Windows (MSVC) but not on Linux (GCC/nvcc). This records the six
portability fixes that take it from "won't compile on Linux" to "builds and serves inference on
Linux", verified on an RTX 4090 under WSL2 (Ubuntu, CUDA 13.0, GCC).

## Fixes (patch files in `agent-bench/`)

1. **`zend-linux-case-fix.patch`** — 13 CUDA sources include the loader headers as `q{3,4,5,6}_k.cuh`,
   but the files are `q{3,4,5,6}_K.cuh`. Builds on case-insensitive Windows, fails on case-sensitive
   Linux.
2. **`zend-linux-halfraw-fix.patch`** — `block_compact.cuh` puts `half`/`half2` scale fields inside
   anonymous `union`/`struct`s. Those types have constructors, and GCC forbids members with
   constructors in an anonymous aggregate; MSVC allows it. The 62 fields move to the POD
   `__half_raw`/`__half2_raw` (identical size and alignment; the existing `sizeof` static-asserts
   still hold, so the packed layout is byte-identical, and the raw types convert implicitly to/from
   `half`/`half2` at every use site).
3. **`zend-linux-cfloat-fix.patch`** — `FLT_MAX` used without `#include <cfloat>` (3 files); MSVC
   pulls it in transitively.
4. **`zend-linux-overload-fix.patch`** — a stale forward declaration of
   `dequant_q8_0_for_4x_mma_k16_runtime` in `kernel.cuh` kept the old runtime-`half_idx` signature
   after the function became a template on `half_idx`. GCC's two-phase lookup binds the call at its
   definition point to the stale declaration and fails; MSVC re-resolves at instantiation. A genuine
   latent bug, not just hygiene.
5. **`zend-linux-atomicadd-fix.patch`** — `atomicAdd` on a `uint64_t*` in `kv_hash.cu`. On LP64 Linux
   `uint64_t` is `unsigned long`, which has no `atomicAdd` overload (only `unsigned long long`); cast
   to `unsigned long long`. On LLP64 Windows `uint64_t` *is* `unsigned long long`, so it matched.
6. **`zend-linux-cstdio-fix.patch`** — `printf` used without `#include <cstdio>` (3 files).

Five are header/hygiene or platform-ABI gaps MSVC tolerated; #4 is a real overload bug a stricter
compiler exposes. All six are layout- and behaviour-neutral: none changes Windows behaviour (the
swapped types and casts are identical there).

## Verification (RTX 4090, WSL2 Ubuntu, CUDA 13.0, GCC)

- `cargo build --release -p zend` → exit 0; 410 MB binary; `zend --help` runs.
- Runtime smoke (`zend-tiny-model.patch` pins Qwen3.5-0.8B so the daemon loads in seconds):
  `/v1/status` reaches `ready` with the model loaded and `engine_connected: true`; a plain
  passthrough turn returns 64 generated tokens; a tool turn returns a well-formed `bash` call
  (`{"command":"ls -la"}`, `finish_reason: tool_calls`). Inference and the tool-call grammar work
  end-to-end on Linux. Responses captured in `agent-bench/logs/zend-linux-smoke{1,2}.json`.

The six fixes (#1-#6) are the portability set; `zend-tiny-model.patch` is a bench-only model override
for a fast smoke and is not part of the port.
