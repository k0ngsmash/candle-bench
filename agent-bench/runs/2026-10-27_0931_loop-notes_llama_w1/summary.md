# 2026-10-27_0931_loop-notes_llama_w1

- Backend: **llama**, 1 parallel agents, 15 tasks
- Resolved: **5 / 15** (submitted 15)
- Wall time: 60.0 min; median task 3.1 min, 61.5 model calls
- Model calls: 910 (0 failed); median 1.71 s, p90 7.19 s
- Tokens: 20,228,802 prompt, 260,303 generated; generation 72.3 t/s across the run, 72.2 t/s per call (median)
- Context per task: median peak 37,691 tokens, largest 64,729
- GPU: mean utilisation 46.1%, peak memory 20205.0 MiB
- Agent exits: {'Submitted': 9, 'LimitsExceeded': 5, 'RepeatedFormatError': 1}
- Looping: median task's most-repeated command issued 2x; 1 task(s) issued one command 5+ times
