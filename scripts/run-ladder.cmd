@echo off
rem Double-click to run the enabled gates in ladder.csv. Close GPU-heavy apps (Ollama, games) first.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-ladder.ps1" %*
echo.
echo Ladder finished - tell Claude.
pause
