@echo off
setlocal
set PYTHONIOENCODING=utf-8
if not defined MGMV_SONG_PYTHON set "MGMV_SONG_PYTHON=%~dp0song-mcp\.venv\Scripts\python.exe"
"%MGMV_SONG_PYTHON%" "%~dp0song-mcp\service.py" --open-browser %*
exit /b %errorlevel%
