@echo off
rem Wikipedia context layer for every day since 1994 (raw zone, resumable). Loads into the DB at the end;
rem if the API holds the database then, re-run: .venv\Scripts\python.exe -m trikal_pipeline.cli fetch-context
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m trikal_pipeline.cli fetch-context --days all >> data\logs\context_backfill.log 2>&1
