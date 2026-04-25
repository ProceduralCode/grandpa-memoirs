@echo off
rem One-click Plaud token refresh. Run this when sync says "sync error" and
rem the message mentions Chrome locks or expired session. Close Chrome first.
pushd "%~dp0"
where py >nul 2>&1 && (py scripts\refresh_token.py) || python scripts\refresh_token.py
echo.
pause
popd
