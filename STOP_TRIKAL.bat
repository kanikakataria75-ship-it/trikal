@echo off
setlocal
title TRIKAL stop
echo   stopping the TRIKAL data server and terminal ...
for %%p in (8000 3000) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr LISTENING') do taskkill /PID %%a /T /F >nul 2>&1
)
echo   stopped.
timeout /t 3 >nul
