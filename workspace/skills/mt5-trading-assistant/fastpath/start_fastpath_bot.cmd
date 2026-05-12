@echo off
REM Starts the fast-path Telegram bot. Used by the "OpenClaw FastPath Bot"
REM Windows Scheduled Task to survive reboots.

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d "%~dp0"

REM Ensure only one instance — kill any existing fastpath_bot.py process
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /v /fo list ^| findstr /i "fastpath_bot.py"') do taskkill /pid %%a /f >nul 2>&1

python fastpath_bot.py
