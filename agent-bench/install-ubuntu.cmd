@echo off
rem Run after the restart that follows install-wsl.cmd. No admin needed.
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0install-ubuntu.ps1"
