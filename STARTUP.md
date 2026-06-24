# 项目启动命令

## 1. 首次安装依赖

```powershell
.\scripts\sync-wxauto4.ps1
cd backend
pip install -e .
```

以后需要拉取 `FreeWisdom/wxauto-4.0` 的新提交时，重新执行
`.\scripts\sync-wxauto4.ps1`。脚本会更新精确提交锁并校验运行时导入来源。

## 2. 启动本地管理页

```powershell
# 先构建前端（首次或更新后）
cd admin-ui
npm install
npm run build

# 启动管理 API + 页面
cd ..
python -m ai_ta_bot.admin_app
```

打开 `http://127.0.0.1:8000`

## 3. React 开发环境（热更新）

终端 1：

```powershell
python -m ai_ta_bot.admin_app
```

终端 2：

```powershell
cd admin-ui
npm run dev
```

打开 `http://127.0.0.1:5173`，`/api` 自动代理到 `8000`。

## 4. 构建前端并查看

```powershell
cd admin-ui
npm run build

cd ..
python -m ai_ta_bot.admin_app
```

访问 `http://127.0.0.1:8000`。

## 5. 启动微信群机器人

确认微信桌面端已登录、`backend\.env` 已配置后再执行：

```powershell
python -m ai_ta_bot
```

注意：
- `ALIBABA_CLOUD_ACCESS_KEY_ID` 和 `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
  必须有阿里云百炼 `sfm:Retrieve` 权限，并能访问配置中的 Workspace。
- `config/bot.yaml` 中每个知识库必须填写百炼 `workspaceId` 和 `indexId`。
- 默认要求显式配置 `LISTEN_GROUPS`，多个群用英文逗号分隔；未配置会拒绝启动。
- `BOT_MENTION_NAMES` 需要填写本账号在群内可能显示的昵称，才能准确识别
  `@机器人` 和引用机器人消息；多个昵称用英文逗号分隔。
- 首次验证保持 `DRY_RUN=true`，确认日志中的拟回复后再关掉。
- `WEB_SEARCH_ENABLED=true` 时，LLM 路由判定需要实时信息或知识库未命中后，
  才使用当前配置的火山引擎/Tavily 联网搜索。

当前两群真实测试使用带硬白名单校验的启动器：

```powershell
.\scripts\start-two-group-test.cmd
```

它只允许“项目研究”和“每日饮食打卡🍽️”，且只响应 `#举手` 开头的问题。
每个群注册独立微信子窗口，不同群可并行处理，同一群保持消息顺序。立即停止时在启动窗口按
`Ctrl+C`。

查看运行状态：

```powershell
Get-Content .\runtime\bot_health.json -Encoding UTF8
Invoke-RestMethod http://127.0.0.1:8000/api/runtime/health
```

## 6. 端口检查

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

停止占用 8000 的进程：

```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```

## 7. 项目自测

```powershell
.\scripts\self-test.ps1
```

该脚本不会启动机器人，也不会读取或发送微信消息。
