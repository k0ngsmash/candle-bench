# 2026-10-26_1836_loop_llama_w1

- Backend: **llama**, 1 parallel agents, 15 tasks
- Resolved: **3 / 15** (submitted 15)
- Wall time: 59.5 min; median task 3.6 min, 75.0 model calls
- Model calls: 1032 (0 failed); median 1.62 s, p90 6.86 s
- Tokens: 24,507,853 prompt, 243,533 generated; generation 68.2 t/s across the run, 72.8 t/s per call (median)
- Context per task: median peak 39,185 tokens, largest 61,500
- GPU: mean utilisation 45.5%, peak memory 21655.0 MiB
- Agent exits: {'Submitted': 8, 'LimitsExceeded': 7}
- Looping: median task's most-repeated command issued 2x; 1 task(s) issued one command 5+ times
