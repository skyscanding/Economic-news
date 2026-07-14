@echo off
REM Launch the interactive web front end and open it in Chrome/Edge.
REM Optional: set a port with  set NEWSAGENT_PORT=9000  before running.
"%~dp0.venv\Scripts\python.exe" -m newsagent.server
