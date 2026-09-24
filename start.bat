@echo off
title OmniStitch Studio
chcp 65001 >nul
cls

echo [*] Starting OmniStitch Studio...
cd /d "%~dp0"
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"
python server.py
if errorlevel 1 pause
