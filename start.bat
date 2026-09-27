@echo off
rem Starts the web console in its own window, opens it in the browser,
rem then runs the desktop app. Close the "FSOC web console" window to stop the server.
cd /d "%~dp0"
start "FSOC web console" python web\dashboard_server.py
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8420/
python main.py
