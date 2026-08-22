@echo off
rem Spark Cockpit - double-click this file to start the local app.
setlocal

set "ROOT=%~dp0.."

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3.10+ is required but was not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this file again.
    pause
    exit /b 1
)

rem Give the server its own window, so closing this launcher never kills a run.
start "Spark Cockpit" /MIN /D "%ROOT%" %PY% -m cockpit %*

echo Spark Cockpit is starting - your browser opens in a moment.
echo If it does not, go to  http://127.0.0.1:8765
echo.
echo The server keeps running in the minimized "Spark Cockpit" window.
echo Closing the browser is safe; closing that window stops the server.
timeout /t 4 /nobreak >nul 2>nul

endlocal
