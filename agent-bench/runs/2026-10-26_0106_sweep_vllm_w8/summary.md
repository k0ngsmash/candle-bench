# 2026-10-26_0106_sweep_vllm_w8

- Backend: **vllm**, 8 parallel agents, 10 tasks
- Resolved: **7 / 10** (submitted 10)
- Wall time: 60.9 min; median task 15.2 min, 43 model calls
- Model calls: 429 (0 failed); median 13.1 s, p90 69.98 s
- Tokens: 8,114,130 prompt, 159,109 generated; generation 43.6 t/s across the run, 10.0 t/s per call (median)
- Context per task: median peak 22,981 tokens, largest 44,341
- GPU: mean utilisation 99.0%, peak memory 23903.0 MiB
- Agent exits: {'Submitted': 9, 'LimitsExceeded': 1}
