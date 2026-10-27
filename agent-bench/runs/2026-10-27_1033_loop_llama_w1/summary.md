# 2026-10-27_1033_loop_llama_w1

- Backend: **llama**, 1 parallel agents, 15 tasks
- Resolved: **4 / 15** (submitted 15)
- Wall time: 47.5 min; median task 2.8 min, 69.5 model calls
- Model calls: 929 (0 failed); median 1.45 s, p90 5.66 s
- Tokens: 19,292,856 prompt, 187,406 generated; generation 65.8 t/s across the run, 71.7 t/s per call (median)
- Context per task: median peak 34,214 tokens, largest 63,414
- GPU: mean utilisation 43.6%, peak memory 20256.0 MiB
- Agent exits: {'Submitted': 9, 'LimitsExceeded': 6}
- Looping: median task's most-repeated command issued 2x; 2 task(s) issued one command 5+ times
