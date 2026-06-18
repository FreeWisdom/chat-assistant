# AI 助教机器人 — 管理后台启动脚本
# 首次使用前请构建前端: cd admin-ui && npm install && npm run build

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== 管理后台 启动中 ===" -ForegroundColor Cyan
Write-Host "管理页: http://127.0.0.1:8000"
Write-Host "按 Ctrl+C 停止`n"

python -m ai_ta_bot.admin_app
