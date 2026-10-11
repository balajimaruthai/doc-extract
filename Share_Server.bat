@echo off
title DocExtract - Share with Team and Clients
cd /d "%~dp0"
if exist "C:\Users\Zynee\anaconda3\python.exe" (
    "C:\Users\Zynee\anaconda3\python.exe" "%~dp0scripts\share_server.py"
) else (
    python "%~dp0scripts\share_server.py"
)
pause
