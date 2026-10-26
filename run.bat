@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

where python >nul 2>nul
if not errorlevel 1 (
    python main.py %*
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3 not found. Install Python 3.9+ with Tkinter: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    py -3 main.py %*
)

if errorlevel 1 pause
