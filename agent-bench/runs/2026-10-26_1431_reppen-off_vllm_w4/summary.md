# 2026-10-26_1431_reppen-off_vllm_w4

- Backend: **vllm**, 4 parallel agents, 15 tasks
- Resolved: **5 / 15** (submitted 15)
- Wall time: 184.0 min; median task 15.7 min, 56.5 model calls
- Model calls: 872 (0 failed); median 10.36 s, p90 66.62 s
- Tokens: 20,279,234 prompt, 382,053 generated; generation 34.6 t/s across the run, 12.5 t/s per call (median)
- Context per task: median peak 34,349 tokens, largest 65,480
- GPU: mean utilisation 99.3%, peak memory 24007.0 MiB
- Agent exits: {'Submitted': 9, 'RepeatedFormatError': 1, 'LimitsExceeded': 5}
- Looping: median task's most-repeated command issued 2x; 3 task(s) issued one command 5+ times
