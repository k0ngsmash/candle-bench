# 2026-10-25_2023_smoke-pin_vllm_w1

- Backend: **vllm**, 1 parallel agents, 2 tasks
- Resolved: **2 / 2** (submitted 2)
- Wall time: 13.4 min; median task 6.2 min, 22 model calls
- Model calls: 71 (0 failed); median 5.85 s, p90 25.36 s
- Tokens: 870,673 prompt, 12,783 generated; generation 15.9 t/s across the run, 16.0 t/s per call (median)
- Context per task: median peak 16,850 tokens, largest 22,782
- GPU: mean utilisation 93.7%, peak memory 23014.0 MiB
- Agent exits: {'Submitted': 2}
