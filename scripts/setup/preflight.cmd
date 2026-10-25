@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preflight.ps1"
echo.
echo Preflight finished. Log: %~dp0preflight.log
pause
