@echo off
REM Run the daily MT5 analyzer and send the report to Telegram.
REM Triggered by Windows Scheduled Task "OpenClaw Daily Report" at 23:55 daily.

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0..\..\.."
python skills\mt5-trading-assistant\scripts\daily_report_to_telegram.py %*
