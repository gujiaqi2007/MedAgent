# MedAgent launcher (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Use python if available, otherwise the Windows py launcher
$pyCmd = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pyCmd = "py -3"
    } else {
        Write-Host "[ERROR] Python not found. Install Python 3.10+ and check Add to PATH."
        exit 1
    }
}

Write-Host "============================================"
Write-Host "  MedAgent launcher"
Write-Host "============================================"
Write-Host "[1/3] Installing dependencies (first run may take a while)..."
& cmd /c "$pyCmd -m pip install -r requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies."
    Write-Host "        If this is a network issue, try the mirror:"
    Write-Host "        $pyCmd -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}

Write-Host "[2/3] Starting server..."
Write-Host "[3/3] Opening http://127.0.0.1:8000"
Write-Host "Close this window to stop the server."

& cmd /c "$pyCmd -m app.main"
