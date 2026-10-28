# 2026-10-28_0938_loop-overnight-b_llama_w1

- Backend: **llama**, 1 parallel agents, 15 tasks
- Resolved: **4 / 15** (submitted 15)
- Wall time: 46.5 min; median task 2.5 min, 61.0 model calls
- Model calls: 896 (0 failed); median 1.62 s, p90 6.33 s
- Tokens: 20,005,801 prompt, 186,864 generated; generation 67.0 t/s across the run, 71.1 t/s per call (median)
- Context per task: median peak 31,612 tokens, largest 60,681
- GPU: mean utilisation 45.5%, peak memory 21011.0 MiB
- Agent exits: {'Submitted': 10, 'LimitsExceeded': 5}
- Looping: median task's most-repeated command issued 2x; 1 task(s) issued one command 5+ times
