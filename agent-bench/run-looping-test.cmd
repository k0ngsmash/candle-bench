@echo off
rem Looping test: the 15 tasks zend got stuck on, with and without zend's held context. ~2-3 hours.
rem Log: agent-bench\logs\run-looping-test.log
wsl.exe -d Ubuntu-24.04 -u bench --cd /mnt/c/Users/k0ng/source/repos/candle-bench/agent-bench -- bash -lc "bash ./run-looping-test.sh 2>&1 | tee logs/run-looping-test.log"
echo.
echo Done - tell Claude.
pause
