# 2026-10-28_0556_loop-overnight-b_vllm_w1

- Backend: **vllm**, 1 parallel agents, 15 tasks
- Resolved: **2 / 15** (submitted 15)
- Wall time: 218.0 min; median task 10.5 min, 50.0 model calls
- Model calls: 808 (0 failed); median 6.66 s, p90 31.62 s
- Tokens: 16,367,744 prompt, 216,567 generated; generation 16.6 t/s across the run, 16.3 t/s per call (median)
- Context per task: median peak 29,300 tokens, largest 64,616
- GPU: mean utilisation 96.8%, peak memory 23976.0 MiB
- Agent exits: {'Submitted': 12, 'LimitsExceeded': 3}
- Looping: median task's most-repeated command issued 2x; 2 task(s) issued one command 5+ times
