@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preflight-wsl.ps1"
echo Done - tell Claude.
pause
