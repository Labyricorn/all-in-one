@echo off
setlocal
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4
set PYTHONIOENCODING=utf-8
if not defined MGMV_SONG_PYTHON set "MGMV_SONG_PYTHON=%~dp0song-mcp\.venv\Scripts\python.exe"
"%MGMV_SONG_PYTHON%" "%~dp0song-mcp\cli.py" %*
exit /b %errorlevel%
