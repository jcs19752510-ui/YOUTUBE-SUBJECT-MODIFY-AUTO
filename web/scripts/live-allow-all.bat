@echo off
cd /d "%~dp0\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0live-allow-all.ps1"
echo.
pause
