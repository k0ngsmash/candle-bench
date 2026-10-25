@echo off
rem Build zend (local Qwen3.6-35B branch), start it standalone, smoke-test passthrough, stop it.
rem Close Ollama/games first. 20-40 minutes. Log: agent-bench\logs\zend-bringup.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0zend-bringup.ps1"
echo Done - tell Claude.
pause
