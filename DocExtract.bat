@echo off
title DocExtract - Offline Document Intelligence
cd /d "%~dp0"
if exist "C:\Users\Zynee\anaconda3\pythonw.exe" (
    start "" "C:\Users\Zynee\anaconda3\pythonw.exe" "%~dp0app_desktop.pyw"
) else (
    start "" pythonw "%~dp0app_desktop.pyw"
)
exit

