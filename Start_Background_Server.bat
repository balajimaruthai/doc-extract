@echo off
title DocExtract - Background Server
cd /d "%~dp0"
echo =======================================================
echo        DocExtract Background Server Launcher
echo =======================================================
echo Starting DocExtract server in the background...

if exist "C:\Users\Zynee\anaconda3\pythonw.exe" (
    set PYW="C:\Users\Zynee\anaconda3\pythonw.exe"
) else (
    set PYW=pythonw
)
set DOCEXTRACT_DEMO=1
set DOCEXTRACT_HOST=0.0.0.0
start "" %PYW% -m uvicorn main:app --app-dir "%~dp0app\backend" --host 0.0.0.0 --port 37240

timeout /t 2 /nobreak >nul

if exist "C:\Users\Zynee\anaconda3\python.exe" (
    "C:\Users\Zynee\anaconda3\python.exe" "%~dp0scripts\share_server.py"
) else (
    python "%~dp0scripts\share_server.py"
)
