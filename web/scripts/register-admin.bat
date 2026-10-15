@echo off
cd /d "%~dp0\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register-admin.ps1"
echo.
pause
