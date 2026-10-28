# 2026-10-27_2355_loop-overnight-a_vllm_w1

- Backend: **vllm**, 1 parallel agents, 15 tasks
- Resolved: **6 / 15** (submitted 15)
- Wall time: 267.0 min; median task 14.4 min, 52.5 model calls
- Model calls: 823 (0 failed); median 7.86 s, p90 39.96 s
- Tokens: 18,826,689 prompt, 270,908 generated; generation 16.9 t/s across the run, 16.6 t/s per call (median)
- Context per task: median peak 36,514 tokens, largest 64,277
- GPU: mean utilisation 97.6%, peak memory 23846.0 MiB
- Agent exits: {'Submitted': 13, 'LimitsExceeded': 2}
- Looping: median task's most-repeated command issued 3x; 1 task(s) issued one command 5+ times
