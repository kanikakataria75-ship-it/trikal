@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -c "from trikal_pipeline.cli import app; app(['build-reported'])" >> data\logs\build_reported.log 2>&1
