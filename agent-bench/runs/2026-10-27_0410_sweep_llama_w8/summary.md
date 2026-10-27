# 2026-10-27_0410_sweep_llama_w8

- Backend: **llama**, 8 parallel agents, 10 tasks
- Resolved: **6 / 10** (submitted 10)
- Wall time: 124.5 min; median task 35.3 min, 37 model calls
- Model calls: 470 (0 failed); median 32.8 s, p90 177.54 s
- Tokens: 9,596,120 prompt, 127,260 generated; generation 17.0 t/s across the run, 4.0 t/s per call (median)
- Context per task: median peak 23,845 tokens, largest 60,292
- GPU: mean utilisation 55.9%, peak memory 23925.0 MiB
- Agent exits: {'Submitted': 7, 'LimitsExceeded': 3}
- Looping: median task's most-repeated command issued 2.0x; 0 task(s) issued one command 5+ times
