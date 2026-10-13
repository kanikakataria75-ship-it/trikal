@echo off
rem Prices up to the last published session + parse what the downloader has fetched. Stop the API first (it writes the DB).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m trikal_pipeline.cli update-daily >> data\logs\update_daily.log 2>&1
