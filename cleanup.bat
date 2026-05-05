@echo off
rem Manual rescue: kill a stuck backend that's holding port 8000.
rem launch.bat already does this automatically; this is a manual fallback
rem if anything ever feels weird.
pushd "%~dp0"
where py >nul 2>&1 && (py scripts\cleanup_server.py) || python scripts\cleanup_server.py
echo.
pause
popd
