@echo off
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
%SystemRoot%\System32	imeout.exe /t 3 /nobreak >nul
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
