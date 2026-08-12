@echo off
if exist "1\python.exe" (
    1\python.exe iseeu.py
) else if exist "py312\python.exe" (
    py312\python.exe iseeu.py
) else if exist "py3122\python.exe" (
    py3122\python.exe iseeu.py
) else (
    echo [ERROR] No Python found. Run first_run.bat first.
)
pause
