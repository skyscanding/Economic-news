@echo off
REM Run the news agent with the project's virtualenv, from anywhere.
REM Forwards all arguments to debug.py, e.g.:  run.bat --sections Technology --no-open
"%~dp0.venv\Scripts\python.exe" "%~dp0debug.py" %*
