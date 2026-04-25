@echo off
rem Try the Python invocations in order of preference. pyw/pythonw run without
rem a console window (best for end-user UX). py/python show a console (visible
rem but works even when Windows' Store-stub python.exe is on PATH).
pushd "%~dp0"
where pyw >nul 2>&1 && (start "" pyw launch.py & goto :done)
where pythonw >nul 2>&1 && (start "" pythonw launch.py & goto :done)
where py >nul 2>&1 && (start "" py launch.py & goto :done)
start "" python launch.py
:done
popd
