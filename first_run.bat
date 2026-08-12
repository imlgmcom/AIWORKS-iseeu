@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Determine Python directory (supports 1, py312, py3122)
set "PYDIR="
if exist "1\python.exe" set "PYDIR=1"
if exist "py312\python.exe" set "PYDIR=py312"
if exist "py3122\python.exe" set "PYDIR=py3122"

REM If Python found, skip download
if defined PYDIR goto :run_setup

REM === Python download bootstrap (ASCII-only to avoid encoding issues) ===
echo ============================================================
echo   First Run Setup - Downloading Python 3.12 ...
echo ============================================================
echo.

set "PYDIR=py312"
if not exist "!PYDIR!" mkdir "!PYDIR!"

set "PY_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PY_ZIP=!PYDIR!\python-embed.zip"

where curl >nul 2>&1
if %ERRORLEVEL%==0 (
    echo Downloading Python via curl...
    curl -L --fail -o "!PY_ZIP!" "!PY_URL!"
) else (
    echo Downloading Python via PowerShell...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!PY_URL!' -OutFile '!PY_ZIP!'"
)

if not exist "!PY_ZIP!" (
    echo [ERROR] Python download failed.
    echo Please download manually from: !PY_URL!
    echo Extract into !PYDIR!\ folder and re-run.
    pause
    exit /b 1
)

echo Extracting...
powershell -NoProfile -Command "Expand-Archive -Path '!PY_ZIP!' -DestinationPath '!PYDIR!' -Force; Remove-Item '!PY_ZIP!'"

if not exist "!PYDIR!\python.exe" (
    echo [ERROR] Python extraction failed.
    pause
    exit /b 1
)

REM Uncomment "import site" in python312._pth
echo Configuring site module...
powershell -NoProfile -Command "$pth='!PYDIR!\python312._pth'; if(Test-Path $pth){$c=Get-Content $pth -Raw; $c=$c -replace '#import site','import site'; Set-Content $pth -Value $c}"

REM Install pip
echo Installing pip...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '!PYDIR!\get-pip.py'"
if exist "!PYDIR!\get-pip.py" (
    !PYDIR!\python.exe !PYDIR!\get-pip.py
    del "!PYDIR!\get-pip.py"
    REM Configure Tsinghua mirror
    (
        echo [global]
        echo index-url = https://pypi.tuna.tsinghua.edu.cn/simple
        echo trusted-host = pypi.tuna.tsinghua.edu.cn
    ) > !PYDIR!\pip.ini
) else (
    echo [WARN] get-pip.py download failed.
)

echo [OK] Python ready.

:run_setup
echo.
echo Starting setup wizard (using !PYDIR!)...
echo.
!PYDIR!\python.exe tools\setup.py
if errorlevel 1 (
    echo.
    echo [ERROR] Setup failed. Please check the output above.
    pause
    exit /b 1
)

echo.
echo Setup complete. Double-click run.bat to start the program.
pause
