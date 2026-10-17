@echo off
rem Nightly: bring prices up to the last published session (no fundamentals parse). Scheduled 19:45 IST by Task Scheduler "TRIKAL daily prices".
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m trikal_pipeline.cli update-daily --no-refresh >> data\logs\update_daily.log 2>&1
