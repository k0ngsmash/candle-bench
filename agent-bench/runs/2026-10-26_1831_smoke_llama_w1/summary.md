# 2026-10-26_1831_smoke_llama_w1

- Backend: **llama**, 1 parallel agents, 2 tasks
- Resolved: **2 / 2** (submitted 2)
- Wall time: 3.5 min; median task 1.3 min, 18 model calls
- Model calls: 63 (0 failed); median 1.39 s, p90 5.45 s
- Tokens: 695,759 prompt, 12,087 generated; generation 57.6 t/s across the run, 72.4 t/s per call (median)
- Context per task: median peak 16,225 tokens, largest 21,127
- GPU: mean utilisation 35.0%, peak memory 20811.0 MiB
- Agent exits: {'Submitted': 2}
- Looping: median task's most-repeated command issued 3.5x; 1 task(s) issued one command 5+ times
