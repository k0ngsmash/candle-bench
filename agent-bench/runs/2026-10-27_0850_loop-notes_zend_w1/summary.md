# 2026-10-27_0850_loop-notes_zend_w1

- Backend: **zend**, 1 parallel agents, 15 tasks
- Resolved: **3 / 15** (submitted 15)
- Wall time: 35.5 min; median task 2.0 min, 75.0 model calls
- Model calls: 1033 (0 failed); median 0.87 s, p90 3.12 s
- Tokens: 21,734,272 prompt, 255,249 generated; generation 119.8 t/s across the run, 125.8 t/s per call (median)
- Context per task: median peak 32,999 tokens, largest 35,317
- GPU: mean utilisation 76.8%, peak memory 23140.0 MiB
- Agent exits: {'Submitted': 4, 'LimitsExceeded': 11}
- Looping: median task's most-repeated command issued 4x; 7 task(s) issued one command 5+ times
