# 2026-10-27_0344_sweep_llama_w1

- Backend: **llama**, 1 parallel agents, 10 tasks
- Resolved: **6 / 10** (submitted 10)
- Wall time: 23.5 min; median task 1.8 min, 36 model calls
- Model calls: 451 (0 failed); median 1.37 s, p90 5.94 s
- Tokens: 8,492,364 prompt, 99,293 generated; generation 70.4 t/s across the run, 71.9 t/s per call (median)
- Context per task: median peak 19,885 tokens, largest 60,656
- GPU: mean utilisation 45.2%, peak memory 20070.0 MiB
- Agent exits: {'Submitted': 7, 'LimitsExceeded': 3}
- Looping: median task's most-repeated command issued 2.0x; 1 task(s) issued one command 5+ times
