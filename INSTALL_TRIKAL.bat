@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title TRIKAL installer
echo.
echo   TRIKAL - one-time installation on this computer
echo   ------------------------------------------------
echo.

rem ---- Python 3.12 or newer ------------------------------------------------------------------------
set "PY="
for %%c in ("py -3.13" "py -3.12" "py -3" "python") do (
  if not defined PY (
    %%~c -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul && set "PY=%%~c"
  )
)
if not defined PY (
  echo   Python 3.12 or newer was not found. Trying to install it with winget ...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo   Python was installed. CLOSE THIS WINDOW and double-click INSTALL_TRIKAL.bat again.
  pause
  exit /b 1
)
echo   Python: %PY%

rem ---- Node.js ---------------------------------------------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
  echo   Node.js was not found. Trying to install it with winget ...
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  echo.
  echo   Node.js was installed. CLOSE THIS WINDOW and double-click INSTALL_TRIKAL.bat again.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('node --version') do echo   Node: %%v

rem ---- Python environment ------------------------------------------------------------------------------
rem a .venv copied from another computer points at that computer's folders and Python: if it does not run here, build a fresh one
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo   the Python environment copied from the other computer does not work here; rebuilding it ...
    rmdir /s /q .venv
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo   creating the Python environment ...
  %PY% -m venv .venv || goto :fail
)
echo   installing the Python packages ^(a few minutes the first time^) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -e . -q || goto :fail

rem ---- Web app ---------------------------------------------------------------------------------------------
echo   installing the terminal ^(web^) packages ^(a few minutes the first time^) ...
pushd web
call npm install --no-audit --no-fund || (popd & goto :fail)
popd

rem ---- Settings ---------------------------------------------------------------------------------------------
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo   created .env from the template: live prices stay off until you add your OWN broker keys there
)

rem ---- Data --------------------------------------------------------------------------------------------------
echo.
if exist "data\trikal.duckdb" (
  echo   The database is here: data\trikal.duckdb
  echo.
  echo   Everything is installed. Double-click TRIKAL.bat to start.
) else (
  echo   The software is installed, but the DATABASE is missing.
  echo   Copy the folder  data  from the computer that has TRIKAL ^(it contains trikal.duckdb^) into this folder,
  echo   so that this file exists:   %cd%\data\trikal.duckdb
  echo   Building the data from scratch is possible but takes days of downloads.
  echo   After copying, double-click TRIKAL.bat.
)
echo.
pause
exit /b 0

:fail
echo.
echo   Something failed above. Take a photo or screenshot of this window and send it to the person who gave you TRIKAL.
pause
exit /b 1
