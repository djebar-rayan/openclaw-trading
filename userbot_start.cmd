@echo off
REM Launch userbot.py in a loop. Restart 10 s after every crash.
REM Run via Windows Task Scheduler ("OpenClaw UserBot") for auto-start at boot.

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d "%~dp0"

:loop
python -u userbot.py >> userbot.log 2>&1
echo [%date% %time%] userbot exited, restarting in 10s >> userbot.log
timeout /t 10 /nobreak > nul
goto loop
