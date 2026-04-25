@echo off
rem Plaud login refresh. Run this when sync says "sync error" or your Plaud
rem login is more than ~30 days old. This script closes Chrome, gets a new
rem login from Plaud, and saves it so the app can sync again.
pushd "%~dp0"
echo.
echo ============================================================
echo   REFRESH PLAUD LOGIN
echo ============================================================
echo.
echo This will:
echo   1. Close all Chrome windows on your computer.
echo   2. Briefly open a Chrome window to log in to Plaud.
echo   3. Close that window automatically.
echo   4. Save the new login so Sync works again.
echo.
echo Before continuing:
echo   - Save anything you have open in Chrome.
echo   - Make sure you can sign in to web.plaud.ai in Chrome
echo     (you should already be signed in).
echo.
echo IMPORTANT: After you press a key below, do NOT touch anything
echo for about 20 seconds. A Chrome window will pop up and close
echo by itself. Wait until you see "Success" before doing anything.
echo.
pause
echo.
echo Closing Chrome...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo Getting your Plaud login...
echo (Hands off the keyboard and mouse for the next ~20 seconds.)
echo.
where py >nul 2>&1 && (py scripts\refresh_token.py) || python scripts\refresh_token.py
echo.
echo ============================================================
echo   When you see "Success" above, you can:
echo     1. Reopen the app (launch.bat or your desktop shortcut)
echo     2. Click "Sync"
echo ============================================================
echo.
pause
popd
