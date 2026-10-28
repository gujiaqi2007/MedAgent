# 健康守护 Agent (MedAgent) 启动脚本（PowerShell）
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "============================================"
Write-Host "  健康守护 Agent (MedAgent) 启动器"
Write-Host "============================================"

# 优先 python，回退到 Windows 官方 py 启动器
$pyCmd = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pyCmd = "py -3"
    } else {
        Write-Host "[错误] 未检测到 Python，请安装 Python 3.10+ 并勾选 Add to PATH。"
        exit 1
    }
}

Write-Host "[1/3] 检查并安装依赖（首次较慢）..."
& cmd /c "$pyCmd -m pip install -r requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[提示] 依赖安装失败。若为网络原因，可用国内镜像重试："
    Write-Host "       $pyCmd -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}

Write-Host "[2/3] 启动服务..."
Write-Host "[3/3] 即将在浏览器打开 http://127.0.0.1:8000"
Write-Host "关闭本窗口即停止服务。"

& cmd /c "$pyCmd -m app.main"
