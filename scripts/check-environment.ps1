# AI 助教机器人 — 环境检查脚本
# PowerShell 7+ / Windows PowerShell 5.1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "=== AI 助教机器人 环境检查 ===" -ForegroundColor Cyan
Write-Host "项目根目录: $Root`n"

# 1. Python 版本
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] Python: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] 未找到 Python，请安装 Python 3.11+" -ForegroundColor Red
    exit 1
}

# 2. 微信版本
Write-Host "[INFO] 请确认桌面微信已登录（微信 4.0.5.x）" -ForegroundColor Yellow

# 3. .env 文件
$envFile = Join-Path $Root "backend\.env"
if (Test-Path $envFile) {
    Write-Host "[OK] .env 已配置: $envFile" -ForegroundColor Green
} else {
    Write-Host "[WARN] .env 不存在，请从 .env.example 复制并填入 API Key" -ForegroundColor Yellow
    Write-Host "       cp backend\.env.example backend\.env"
}

# 4. 配置文件
$configFile = Join-Path $Root "config\bot.yaml"
if (Test-Path $configFile) {
    Write-Host "[OK] bot.yaml 已配置: $configFile" -ForegroundColor Green
} else {
    Write-Host "[FAIL] config\bot.yaml 不存在" -ForegroundColor Red
}

# 5. 知识库数据
$kbDir = Join-Path $Root "knowledge-data"
if (Test-Path $kbDir) {
    $kbCount = (Get-ChildItem -Path $kbDir -Recurse -File | Measure-Object).Count
    Write-Host "[OK] 知识库数据: $kbDir ($kbCount 个文件)" -ForegroundColor Green
} else {
    Write-Host "[WARN] knowledge-data 目录不存在" -ForegroundColor Yellow
}

# 6. 运行目录
$runtimeDir = Join-Path $Root "runtime"
if (-not (Test-Path $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir, "$runtimeDir\logs", "$runtimeDir\backups", "$runtimeDir\vector_store" -Force | Out-Null
    Write-Host "[OK] 已创建 runtime 目录结构" -ForegroundColor Green
} else {
    Write-Host "[OK] runtime 目录已就绪" -ForegroundColor Green
}

# 7. 依赖检查
try {
    pip show ai-ta-bot 2>&1 | Out-Null
    # Actually check for our package
    $pkgCheck = pip show ai_ta_bot 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] ai_ta_bot 包已安装" -ForegroundColor Green
    } else {
        Write-Host "[WARN] ai_ta_bot 包未安装，请运行: cd backend && pip install -e ." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] 无法检查包安装状态" -ForegroundColor Yellow
}

# 8. admin-ui
$adminDist = Join-Path $Root "admin-ui\dist\index.html"
if (Test-Path $adminDist) {
    Write-Host "[OK] admin-ui 已构建" -ForegroundColor Green
} else {
    Write-Host "[WARN] admin-ui 未构建，请运行: cd admin-ui && npm install && npm run build" -ForegroundColor Yellow
}

Write-Host "`n=== 检查完成 ===" -ForegroundColor Cyan
Write-Host "启动机器人: .\scripts\start-bot.ps1"
Write-Host "启动管理页: .\scripts\start-admin.ps1"
