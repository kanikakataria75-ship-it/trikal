@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -c "from trikal_pipeline.cli import app; app(['fetch-calls'])" >> data\logs\fetch_calls.log 2>&1
