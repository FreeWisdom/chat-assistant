# AI 助教机器人 — 启动脚本
# 启动前请确认：
#   1. 桌面微信已登录
#   2. backend\.env 已配置 DeepSeek API Key
#   3. config\bot.yaml 已配置群绑定
#   4. pip install -e backend/ 已完成

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== AI 助教机器人 启动中 ===" -ForegroundColor Cyan
Write-Host "项目根目录: $Root"
Write-Host "按 Ctrl+C 停止`n"

python -m ai_ta_bot
