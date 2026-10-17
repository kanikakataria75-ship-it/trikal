@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -c "from trikal_pipeline.cli import app; app(['build-calls'])" >> data\logs\build_calls.log 2>&1
