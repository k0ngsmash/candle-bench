# 2026-10-26_0228_sweep_vllm_w1

- Backend: **vllm**, 1 parallel agents, 10 tasks
- Resolved: **6 / 10** (submitted 10)
- Wall time: 136.0 min; median task 7.4 min, 35 model calls
- Model calls: 452 (1 failed); median 7.08 s, p90 46.11 s
- Tokens: 9,432,074 prompt, 137,440 generated; generation 16.8 t/s across the run, 16.3 t/s per call (median)
- Context per task: median peak 25,467 tokens, largest 65,528
- GPU: mean utilisation 97.5%, peak memory 23620.0 MiB
- Agent exits: {'Submitted': 8, 'ContextWindowExceededError': 1, 'LimitsExceeded': 1}
