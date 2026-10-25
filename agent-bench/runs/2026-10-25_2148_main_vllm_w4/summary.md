# 2026-10-25_2148_main_vllm_w4

- Backend: **vllm**, 4 parallel agents, 30 tasks
- Resolved: **15 / 30** (submitted 30)
- Wall time: 175.8 min; median task 15.0 min, 44 model calls
- Model calls: 1382 (0 failed); median 12.27 s, p90 64.84 s
- Tokens: 29,781,472 prompt, 467,870 generated; generation 44.3 t/s across the run, 11.9 t/s per call (median)
- Context per task: median peak 28,997 tokens, largest 65,030
- GPU: mean utilisation 99.7%, peak memory 24022.0 MiB
- Agent exits: {'Submitted': 26, 'LimitsExceeded': 4}
