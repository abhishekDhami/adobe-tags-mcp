@echo off
setlocal
cd /d "%~dp0"
REM Repo-root shared venv (adobeTagsMCP\.venv)
"%~dp0..\.venv\Scripts\python.exe" -m app.server
