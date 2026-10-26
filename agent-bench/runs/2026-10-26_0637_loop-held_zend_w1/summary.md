# 2026-10-26_0637_loop-held_zend_w1

- Backend: **zend**, 1 parallel agents, 15 tasks
- Resolved: **1 / 15** (submitted 15)
- Wall time: 32.5 min; median task 2.1 min, 75.0 model calls
- Model calls: 1064 (0 failed); median 0.73 s, p90 3.81 s
- Tokens: 22,567,472 prompt, 243,360 generated; generation 124.8 t/s across the run, 135.0 t/s per call (median)
- Context per task: median peak 33,002 tokens, largest 34,650
- GPU: mean utilisation 74.1%, peak memory 23472.0 MiB
- Agent exits: {'Submitted': 4, 'LimitsExceeded': 11}
- Looping: median task's most-repeated command issued 5x; 8 task(s) issued one command 5+ times
