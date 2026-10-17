@echo off
setlocal
cd /d "%~dp0"
title TRIKAL launcher
echo.
echo   TRIKAL - starting the terminal. Keep this window open until the browser opens.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo   The Python environment is missing: .venv\Scripts\python.exe
  pause
  exit /b 1
)

call :up 8000 api
if errorlevel 1 (
  echo   starting the data server ^(API, port 8000^) ...
  start "TRIKAL API" /min cmd /c ".venv\Scripts\python.exe -m uvicorn trikal_api.app:app --app-dir api --host 127.0.0.1 --port 8000"
) else (
  echo   data server already running
)

call :up 3000 web
if errorlevel 1 (
  echo   starting the terminal ^(web, port 3000^) ...
  start "TRIKAL WEB" /min cmd /c "cd /d web && npm run dev"
) else (
  echo   terminal already running
)

echo   waiting for the terminal to be ready ^(the first start takes up to a minute^) ...
for /l %%i in (1,1,90) do (
  call :up 3000 web
  if not errorlevel 1 goto ready
  %SystemRoot%\System32	imeout.exe /t 2 /nobreak >nul
)
echo   the terminal did not start in time. Look at the "TRIKAL WEB" window for the error.
pause
exit /b 1

:ready
echo   opening the browser ...
start "" "http://localhost:3000/terminal"
echo.
echo   Done. This window can be closed; the terminal keeps running.
echo   To stop everything: run STOP_TRIKAL.bat
%SystemRoot%\System32	imeout.exe /t 6 >nul
exit /b 0

:up
rem any answer from the port counts as up (the data server answers 503 while the pipeline is writing)
powershell -NoProfile -Command "$r = try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri ('http://127.0.0.1:' + '%1' + $(if ('%2' -eq 'api') {'/api/meta?as_of=NOW'} else {'/'})) } catch { $_.Exception.Response }; if ($r) { exit 0 } else { exit 1 }"
exit /b %errorlevel%
