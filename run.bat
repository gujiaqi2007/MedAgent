@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Use python if available, otherwise the Windows py launcher
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 goto no_python
    set "PY=py -3"
)

echo ============================================
echo   MedAgent launcher
echo ============================================
echo.

echo [1/3] Installing dependencies (first run may take a while)...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed

%PY% -c "import starlette, uvicorn, pydantic" >nul 2>nul
if errorlevel 1 goto pip_failed

echo [2/3] Starting server...
echo [3/3] Opening http://127.0.0.1:8000 in your browser.
echo       Close this window to stop the server.
echo.
%PY% -m app.main
goto end

:no_python
echo.
echo [ERROR] Python was not found.
echo         Install Python 3.10+ from https://www.python.org/downloads/
echo         and check "Add python.exe to PATH" during installation.
goto end

:pip_failed
echo.
echo [ERROR] Failed to install dependencies.
echo         If this is a network issue, try the mirror:
echo         %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
goto end

:end
echo.
pause
