@echo off
rem OpenClaw Gateway launcher.

set "TMPDIR=C:\Users\ADMINI~1\AppData\Local\Temp"
set "HTTP_PROXY=http://127.0.0.1:7897"
set "HTTPS_PROXY=http://127.0.0.1:7897"
set "ALL_PROXY=http://127.0.0.1:7897"
set "NO_PROXY=localhost,127.0.0.1,::1"
set "http_proxy=http://127.0.0.1:7897"
set "https_proxy=http://127.0.0.1:7897"
set "all_proxy=http://127.0.0.1:7897"
set "no_proxy=localhost,127.0.0.1,::1"
set "OPENCLAW_GATEWAY_PORT=18789"
set "OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service"
set "OPENCLAW_WINDOWS_TASK_NAME=OpenClaw Gateway"
set "OPENCLAW_SERVICE_MARKER=openclaw"
set "OPENCLAW_SERVICE_KIND=gateway"
set "OPENCLAW_SERVICE_VERSION=2026.5.7"

D:\nodejs\node.exe D:\nodejs\node_modules\openclaw\dist\index.js gateway --port 18789

