# 2026-10-27_0616_loop-default_vllm_w4

- Backend: **vllm**, 4 parallel agents, 15 tasks
- Resolved: **3 / 15** (submitted 15)
- Wall time: 149.0 min; median task 18.7 min, 54.5 model calls
- Model calls: 825 (0 failed); median 13.03 s, p90 73.96 s
- Tokens: 19,019,525 prompt, 306,305 generated; generation 34.3 t/s across the run, 12.2 t/s per call (median)
- Context per task: median peak 32,714 tokens, largest 64,362
- GPU: mean utilisation 99.5%, peak memory 24064.0 MiB
- Agent exits: {'Submitted': 9, 'LimitsExceeded': 6}
- Looping: median task's most-repeated command issued 2x; 2 task(s) issued one command 5+ times
