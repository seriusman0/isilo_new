@echo off
title iSilo Recovery
cd /d "%~dp0"
python "%~dp0isilo_recovery.py" %*
if errorlevel 1 (
    echo.
    echo ERROR: Could not start iSilo Recovery.
    echo Make sure Python 3.8+ is installed.
    echo Download: https://www.python.org/downloads/
    pause
)
