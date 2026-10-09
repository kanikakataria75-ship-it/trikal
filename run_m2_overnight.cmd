@echo off
REM Overnight M2 raw download (resumable). Safe to close Claude; keep the laptop awake and plugged in.
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
".venv\Scripts\trikal.exe" fetch-m2 >> "data\logs\m2_overnight.log" 2>&1
