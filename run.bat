@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   健康守护 Agent (MedAgent) 启动器
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选"Add to PATH"。
    pause
    exit /b 1
)

echo [1/3] 检查并安装依赖...
python -m pip install -r requirements.txt -q

echo [2/3] 启动服务...
echo [3/3] 即将在浏览器打开 http://127.0.0.1:8000
echo 关闭本窗口即停止服务。
echo.
python -m app.main

pause
