# 2026-10-26_1937_main_llama_w4

- Backend: **llama**, 4 parallel agents, 30 tasks
- Resolved: **17 / 30** (submitted 30)
- Wall time: 70.5 min; median task 8.8 min, 59 model calls
- Model calls: 1613 (0 failed); median 5.0 s, p90 20.5 s
- Tokens: 32,199,416 prompt, 353,734 generated; generation 83.6 t/s across the run, 23.9 t/s per call (median)
- Context per task: median peak 32,095 tokens, largest 59,459
- GPU: mean utilisation 43.1%, peak memory 24043.0 MiB
- Agent exits: {'Submitted': 22, 'LimitsExceeded': 8}
- Looping: median task's most-repeated command issued 2.0x; 1 task(s) issued one command 5+ times
