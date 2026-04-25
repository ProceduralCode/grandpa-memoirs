@echo off
rem One-click Plaud token refresh. Run this when sync says "sync error" and
rem the message mentions Chrome locks or expired session.
rem
rem This forcibly closes ALL Chrome windows (including background processes
rem that hold file locks even after windows look closed).
pushd "%~dp0"
echo This will CLOSE all Chrome windows on your computer.
echo Save anything important in Chrome first, then continue.
echo.
pause
echo.
echo Closing Chrome processes...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo Done. Now extracting Plaud token...
echo.
where py >nul 2>&1 && (py scripts\refresh_token.py) || python scripts\refresh_token.py
echo.
pause
popd
