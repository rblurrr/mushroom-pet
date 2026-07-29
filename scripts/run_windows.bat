@echo off
setlocal
cd /d "%~dp0.."

set PY=
where pythonw.exe >nul 2>&1 && set PY=pythonw.exe
if "%PY%"=="" ( where py.exe >nul 2>&1 && set PY=py.exe -3 )
if "%PY%"=="" ( where python.exe >nul 2>&1 && set PY=python.exe )
if "%PY%"=="" (
  echo.
  echo   Python 3 was not found.
  echo   Install it from https://www.python.org/downloads/windows/
  echo   and tick "Add python.exe to PATH" in the installer.
  echo.
  pause
  exit /b 1
)

%PY% -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo Installing PySide6 ^(one time, ~100 MB^)...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 ( echo Install failed. & pause & exit /b 1 )
)

where pythonw.exe >nul 2>&1
if not errorlevel 1 ( start "" pythonw.exe run.py ) else ( start "" %PY% run.py )
exit /b 0
