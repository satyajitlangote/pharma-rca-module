@echo off
rem Launches ONE uvicorn instance for the AIVOA RCA backend.
rem Managed by start_backend.ps1 (Task Scheduler task AIVOA-RCA-Backend).
rem stdout/stderr append to the shared log so history is preserved.
rem All paths are derived from this file's location so a fresh clone works
rem without editing (the venv must exist first: see README step 2).
setlocal
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
if not exist "%TEMP%\aivoa-rca" mkdir "%TEMP%\aivoa-rca"
"%~dp0venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%TEMP%\aivoa-rca\aivoa_uvicorn.log" 2>&1
