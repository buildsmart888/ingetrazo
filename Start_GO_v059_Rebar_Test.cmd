@echo off
rem SPDX-License-Identifier: GPL-3.0-or-later
setlocal EnableExtensions DisableDelayedExpansion
rem v0.5.9 source-test launcher. Keep it beside main.py.
cd /d "%~dp0"
if not "%ERRORLEVEL%"=="0" goto failed
if not exist "main.py" (
    echo ERROR: Extract the complete branch ZIP and run this file beside main.py.
    goto failed
)
if not exist "requirements-rebar-v059-test.txt" (
    echo ERROR: requirements-rebar-v059-test.txt is missing.
    goto failed
)

if exist ".venv-rebar\Scripts\python.exe" goto check_environment
set "REBAR_PY_ARGS=-3.12"
py -3.12 -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto create_environment
set "REBAR_PY_ARGS=-3"
py -3 -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo ERROR: Install 64-bit Python 3.12 or newer with the Python launcher.
    goto failed
)

:create_environment
echo Creating the local GO + v0.5.9 rebar test environment...
py %REBAR_PY_ARGS% -m venv ".venv-rebar"
if not "%ERRORLEVEL%"=="0" goto failed

:check_environment
".venv-rebar\Scripts\python.exe" -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize('P') == 8 else 1)"
if not "%ERRORLEVEL%"=="0" (
    echo ERROR: Existing .venv-rebar is not a working 64-bit Python 3.12+ environment.
    echo Rename or delete that folder and run this launcher again.
    goto failed
)
".venv-rebar\Scripts\python.exe" -c "import PySide6, numpy, ezdxf, manifold3d" >nul 2>&1
if "%ERRORLEVEL%"=="0" goto start_application
echo Installing the limited GO + v0.5.9 rebar-test dependencies...
".venv-rebar\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements-rebar-v059-test.txt"
if not "%ERRORLEVEL%"=="0" goto failed

:start_application
echo Starting GO + IngeTrazo v0.5.9 + Rebar LOD in a separate process...
echo Installed C:\Program Files\IngeTrazo is not replaced.
".venv-rebar\Scripts\python.exe" "%~dp0main.py" --new-window
if not "%ERRORLEVEL%"=="0" goto failed
exit /b 0

:failed
echo.
echo The GO + v0.5.9 rebar test host could not start. Read the error above.
pause
exit /b 1
