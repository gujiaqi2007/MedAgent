@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   健康守护 Agent (MedAgent) 启动器
echo ============================================
echo.

rem 优先使用 python，找不到则回退到 Windows 官方 py 启动器
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [错误] 未检测到 Python。
        echo        请到 https://www.python.org/downloads/ 安装 Python 3.10+ ，
        echo        并在安装时勾选 "Add python.exe to PATH"。
        echo.
        pause
        exit /b 1
    )
    set "PY=py -3"
)

echo [1/3] 检查并安装依赖（首次运行较慢，请耐心等待）...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [提示] 依赖安装失败。若为网络原因，可改用国内镜像后重试：
    echo        %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    pause
    exit /b 1
)

echo [2/3] 启动服务...
echo [3/3] 即将在浏览器打开 http://127.0.0.1:8000
echo       关闭本窗口即停止服务。
echo.
%PY% -m app.main

pause
