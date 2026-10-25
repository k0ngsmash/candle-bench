@echo off
rem The main comparison (30 tasks x 2 engines at 4 agents, then 1 and 8 agents on 10 tasks).
rem Unattended, roughly 4-6 hours. Close Ollama/games and leave the PC on (disable sleep).
rem Log: agent-bench\logs\run-main.log
wsl.exe -d Ubuntu-24.04 -u bench --cd /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench -- bash -lc "bash ./run-main.sh 2>&1 | tee logs/run-main.log"
echo.
echo Done - tell Claude.
pause
