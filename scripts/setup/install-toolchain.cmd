@echo off
rem Re-launches the installer elevated (you will get one UAC prompt).
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -NoExit -File \"%~dp0install-toolchain.ps1\"'"
