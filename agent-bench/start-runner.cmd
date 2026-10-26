@echo off
title candle-bench job runner (close to stop)
rem Runs queued jobs from agent-bench\queue while this window stays open. Nothing starts it
rem automatically: closing this window, logging out or rebooting stops it.
if exist "%~dp0queue\STOP" del "%~dp0queue\STOP"
wsl.exe -d Ubuntu-24.04 -u bench -- bash /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench/runner/queue-runner.sh
echo.
echo Runner ended.
pause
