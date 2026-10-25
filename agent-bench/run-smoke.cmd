@echo off
rem End-to-end smoke test: 2 SWE-bench Lite tasks on zend, then the same 2 on vLLM, then scoring.
rem Close Ollama/games first. Roughly 1-2 hours. Log: agent-bench\logs\run-smoke.log
wsl.exe -d Ubuntu-24.04 -u bench --cd /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench -- bash -lc "bash ./run-smoke.sh 2>&1 | tee logs/run-smoke.log"
echo.
echo Done - tell Claude.
pause
