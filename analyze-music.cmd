@echo off
setlocal
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4
"%~dp0.venv\Scripts\allin1.exe" --no-multiprocess %*
exit /b %errorlevel%
