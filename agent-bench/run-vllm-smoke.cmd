@echo off
rem Re-score the zend smoke run, then smoke-test vLLM. Log: agent-bench\logs\run-vllm-smoke.log
wsl.exe -d Ubuntu-24.04 -u bench --cd /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench -- bash -lc "bash ./run-vllm-smoke.sh 2>&1 | tee logs/run-vllm-smoke.log"
echo.
echo Done - tell Claude.
pause
