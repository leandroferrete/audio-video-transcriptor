@echo off
setlocal
cd /d "%~dp0"

set "PY=%cd%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Abrindo GUI...
"%PY%" "%cd%\transcribe_gui.py"

endlocal
