@echo off
title OmniStitch Studio
chcp 65001 >nul
cls

cd /d "%~dp0"
python server.py
if errorlevel 1 pause
