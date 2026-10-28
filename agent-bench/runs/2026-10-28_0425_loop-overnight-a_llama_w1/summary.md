# 2026-10-28_0425_loop-overnight-a_llama_w1

- Backend: **llama**, 1 parallel agents, 15 tasks
- Resolved: **5 / 15** (submitted 15)
- Wall time: 50.0 min; median task 3.2 min, 68.5 model calls
- Model calls: 946 (0 failed); median 1.68 s, p90 5.89 s
- Tokens: 21,430,244 prompt, 200,538 generated; generation 66.8 t/s across the run, 72.8 t/s per call (median)
- Context per task: median peak 36,457 tokens, largest 55,983
- GPU: mean utilisation 43.8%, peak memory 20480.0 MiB
- Agent exits: {'Submitted': 8, 'LimitsExceeded': 7}
- Looping: median task's most-repeated command issued 2x; 1 task(s) issued one command 5+ times
