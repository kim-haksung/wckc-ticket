@echo off
chcp 65001 > nul

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found. Install Python 3.10+ and add to PATH.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

python "%~dp0start_server.py"
pause
