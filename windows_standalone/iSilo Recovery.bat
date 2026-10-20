@echo off
title iSilo Recovery
:: iSilo Recovery - Windows PDB Document Reader
:: Developer: seriusman0@gmail.com
:: Double-click this file to launch iSilo Recovery

echo Starting iSilo Recovery...
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%isilo_recovery.py" %*
if errorlevel 1 (
    echo.
    echo ERROR: Could not start iSilo Recovery.
    echo Make sure Python 3.8+ is installed.
    echo Download Python from: https://www.python.org/downloads/
    pause
)
