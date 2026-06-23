@echo off
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
python -u scripts\start-two-group-test.py
echo.
echo Bot process exited. Press any key to close this window.
pause >nul
