@echo off
rem Installs vLLM, mini-swe-agent and the SWE-bench harness inside Ubuntu, and downloads the 4-bit
rem model for vLLM (~25 GB). 20-40 minutes. Log: agent-bench\logs\setup-bench.log
wsl.exe -d Ubuntu-24.04 -u bench --cd /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench -- bash -lc "bash ./setup-bench.sh 2>&1 | tee logs/setup-bench.log"
echo.
echo Done - tell Claude.
pause
