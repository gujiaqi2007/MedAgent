# 健康守护 Agent (MedAgent) 启动脚本（PowerShell）
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "============================================"
Write-Host "  健康守护 Agent (MedAgent) 启动器"
Write-Host "============================================"

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH。"
    exit 1
}

Write-Host "[1/3] 检查并安装依赖..."
python -m pip install -r requirements.txt -q

Write-Host "[2/3] 启动服务..."
Write-Host "[3/3] 即将在浏览器打开 http://127.0.0.1:8000"
Write-Host "关闭本窗口即停止服务。"

python -m app.main
