@echo off
rem OpenClaw Gateway watchdog.
rem Runs as SYSTEM from Windows Task Scheduler and restarts the gateway if it exits.
rem Keep every "set" on its own line. Do not combine with && because cmd can
rem accidentally include trailing spaces in environment variable values.

set "USERPROFILE=C:\Users\Administrator"
set "HOMEDRIVE=C:"
set "HOMEPATH=\Users\Administrator"
set "HOME=C:\Users\Administrator"
set "APPDATA=C:\Users\Administrator\AppData\Roaming"
set "LOCALAPPDATA=C:\Users\Administrator\AppData\Local"
set "TMPDIR=C:\Users\Administrator\AppData\Local\Temp"
set "TEMP=C:\Users\Administrator\AppData\Local\Temp"
set "TMP=C:\Users\Administrator\AppData\Local\Temp"

set "PATH=D:\nodejs;C:\Users\Administrator\AppData\Roaming\npm;C:\Users\Administrator\AppData\Local\Programs\Python\Python314;C:\Users\Administrator\AppData\Local\Programs\Python\Python314\Scripts;%PATH%"
set "OPENVIKING_PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
set "PYTHONIOENCODING=utf-8"

set "OPENCLAW_GATEWAY_PORT=18789"
set "OPENCLAW_WINDOWS_TASK_NAME=OpenClaw Gateway"
set "OPENCLAW_SERVICE_KIND=gateway"

set "RESTART_DELAY=5"
set "LOGDIR=%TMPDIR%\openclaw"
set "LOGFILE=%LOGDIR%\gateway-watchdog.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

:loop
echo [%date% %time%] Starting OpenClaw Gateway... >> "%LOGFILE%"
D:\nodejs\node.exe D:\nodejs\node_modules\openclaw\dist\index.js gateway --port 18789
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] Gateway exited with code %EXIT_CODE%, restarting in %RESTART_DELAY%s... >> "%LOGFILE%"
timeout /t %RESTART_DELAY% /nobreak >nul
goto loop

