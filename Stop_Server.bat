@echo off
title DocExtract - Stop Server
cd /d "%~dp0"
echo =======================================================
echo          DocExtract - Stopping Server
echo =======================================================
echo Terminating running DocExtract processes...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :37240') do taskkill /F /PID %%a >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1

echo [OK] All DocExtract background server and tunnel processes have been stopped.
echo.
pause
