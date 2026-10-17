"""Writes INSTALL_TRIKAL.bat and PACK_FOR_FRIEND.bat (CRLF, ASCII) in the project root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSTALL = r'''@echo off
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
'''

PACK = r'''@echo off
setlocal
cd /d "%~dp0"
title TRIKAL - pack for a friend
set "OUT=%~dp0..\TRIKAL_for_friend"
echo.
echo   Packing TRIKAL for another computer.
echo   NEVER included: your .env (broker keys), .git, .venv, node_modules, raw downloads, logs.
echo.
echo   Stopping the terminal first so the database file is complete ...
call "%~dp0STOP_TRIKAL.bat" >nul 2>nul
timeout /t 3 /nobreak >nul
tasklist /fi "imagename eq python.exe" /nh | find /i "python.exe" >nul && (
  echo   A Python job is still running ^(a download or a build^). Wait for it to finish, then run this again.
  pause
  exit /b 1
)
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%\data\kasauti" 2>nul

echo   1/3 the program files ...
tar -a -c -f "%OUT%\TRIKAL_program.zip" --exclude=.venv --exclude=node_modules --exclude=.next --exclude=.env --exclude=.git --exclude=data --exclude=__pycache__ --exclude=.claude --exclude=*.pyc .
if errorlevel 1 ( echo   packing failed & pause & exit /b 1 )

echo   2/3 the database ^(about 3 GB, a minute or two^) ...
copy /y "data\trikal.duckdb" "%OUT%\data\trikal.duckdb" >nul
if exist "data\kasauti\report_v1.json" copy /y "data\kasauti\report_v1.json" "%OUT%\data\kasauti\" >nul

echo   3/3 instructions ...
(
echo TRIKAL on a new computer
echo ------------------------
echo 1. Copy this whole folder to the new laptop ^(pen drive^). Keep at least 8 GB free.
echo 2. Unzip TRIKAL_program.zip into a folder such as C:\TRIKAL
echo 3. Copy the folder "data" from here into C:\TRIKAL ^(so C:\TRIKAL\data\trikal.duckdb exists^)
echo 4. Double-click INSTALL_TRIKAL.bat in C:\TRIKAL ^(needs internet; installs Python and Node if missing^)
echo 5. Double-click TRIKAL.bat. The browser opens the terminal.
echo.
echo Live prices need the owner's own broker keys. They are NOT included: the terminal works without them ^(end-of-day prices^).
echo This is a personal research tool, not investment advice.
) > "%OUT%\READ_ME_FIRST.txt"

echo.
echo   Done. Copy this folder to the pen drive:
echo   %OUT%
echo.
pause
'''

(ROOT / "INSTALL_TRIKAL.bat").write_bytes(INSTALL.replace("\n", "\r\n").encode("ascii"))
(ROOT / "PACK_FOR_FRIEND.bat").write_bytes(PACK.replace("\n", "\r\n").encode("ascii"))
print("written")
