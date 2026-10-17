@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -c "from trikal_pipeline.cli import app; app(['kasauti-backtest'])" >> data\logs\kasauti_backtest.log 2>&1
