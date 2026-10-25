@echo off
rem Re-launches the CUDA step elevated (one UAC prompt).
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0install-cuda.ps1\"'"
