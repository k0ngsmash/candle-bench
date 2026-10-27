# 2026-10-27_1123_loop-notes_vllm_w4

- Backend: **vllm**, 4 parallel agents, 15 tasks
- Resolved: **4 / 15** (submitted 15)
- Wall time: 117.0 min; median task 20.8 min, 67.0 model calls
- Model calls: 905 (0 failed); median 11.91 s, p90 67.9 s
- Tokens: 22,769,938 prompt, 312,441 generated; generation 44.5 t/s across the run, 12.4 t/s per call (median)
- Context per task: median peak 36,380 tokens, largest 64,787
- GPU: mean utilisation 98.9%, peak memory 23749.0 MiB
- Agent exits: {'Submitted': 10, 'LimitsExceeded': 5}
- Looping: median task's most-repeated command issued 3x; 1 task(s) issued one command 5+ times
