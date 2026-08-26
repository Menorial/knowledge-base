# ============================================================
# 个人知识库 - 一键启动脚本（Windows PowerShell）
# 用法：
#   1. 首次使用：  .\start.ps1           （自动创建 .venv 并安装依赖）
#   2. 日常使用：  .\start.ps1 -SkipInstall
# ============================================================
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "========================================"
Write-Host " 个人知识库启动器"
Write-Host "========================================"

# ---------- 0. 检查 .env ----------
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "[提示] 已从 .env.example 生成 .env，请填入你的 AI_API_KEY 后重启。"
    Write-Host "       也可以启动后在前端「设置」页直接填写保存。"
}

# ---------- 1. 后端虚拟环境 ----------
if (-not $SkipInstall) {
    if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
        Write-Host "[1/3] 创建 Python 虚拟环境..."
        python -m venv "$root\.venv"
    }
    Write-Host "[1/3] 安装后端依赖（首次较慢，之后跳过）..."
    & "$root\.venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple `
        -r "$root\backend\requirements.txt" | Out-Null
    Write-Host "      依赖安装完成。"
} else {
    if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
        Write-Host "[错误] 未找到 .venv，请先运行 .\start.ps1（不带 -SkipInstall）" -ForegroundColor Red
        exit 1
    }
    Write-Host "[1/3] 使用现有虚拟环境。"
}

# ---------- 2. 前端依赖 ----------
if (-not $SkipInstall) {
    if (-not (Test-Path "$root\frontend\node_modules")) {
        Write-Host "[2/3] 安装前端依赖..."
        Push-Location "$root\frontend"
        npm install | Out-Null
        Pop-Location
    } else {
        Write-Host "[2/3] 前端依赖已存在。"
    }
} else {
    Write-Host "[2/3] 跳过前端依赖检查。"
}

# ---------- 3. 启动服务 ----------
Write-Host "[3/3] 启动服务..."

$backendLog = "$root\backend.log"
$frontendLog = "$root\frontend.log"

# 清理旧日志
Remove-Item $backendLog, $frontendLog -ErrorAction SilentlyContinue

# 后端（--reload 便于开发，生产可去掉）
$backend = Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8000","--reload" `
    -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err" -PassThru

# 前端
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c","npm run dev > `"$frontendLog`" 2>&1" `
    -WorkingDirectory "$root\frontend" -WindowStyle Hidden -PassThru

Write-Host ""
Write-Host "  ✅ 后端  http://localhost:8000   (PID $($backend.Id))   日志: backend.log"
Write-Host "  ✅ 前端  http://localhost:5173   (PID $($frontend.Id))  日志: frontend.log"
Write-Host ""
Write-Host "  浏览器打开 http://localhost:5173 即可使用"
Write-Host "  停止服务：Stop-Process -Id $($backend.Id),$($frontend.Id) -Force"
Write-Host ""
