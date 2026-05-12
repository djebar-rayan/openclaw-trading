@echo off
rem OpenClaw Gateway launcher
rem Adjust the path on line below to your local Node.js + OpenClaw install.
set "TMPDIR=%TEMP%"
set "OPENCLAW_GATEWAY_PORT=18789"
set "OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service"
set "OPENCLAW_WINDOWS_TASK_NAME=OpenClaw Gateway"
set "OPENCLAW_SERVICE_MARKER=openclaw"
set "OPENCLAW_SERVICE_KIND=gateway"
set "OPENCLAW_SERVICE_VERSION=2026.5.2"
"%ProgramFiles%\nodejs\node.exe" "%APPDATA%\npm\node_modules\openclaw\dist\index.js" gateway --port 18789
