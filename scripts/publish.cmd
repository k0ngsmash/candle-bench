@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
echo.
echo Published - tell Claude.
pause
