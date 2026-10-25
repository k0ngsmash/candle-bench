@echo off
rem Installs WSL2 (one admin prompt). Restart Windows afterwards.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0install-wsl.ps1\"'"
