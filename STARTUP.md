# 项目启动命令

## 1. 首次安装依赖

```powershell
cd backend
pip install -e .
```

可选向量检索：

```powershell
pip install -e ".[vector]"
```

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
- MVP 默认要求显式配置 `TEST_GROUP`，未配置会拒绝启动。
- 首次验证保持 `DRY_RUN=true`，确认日志中的拟回复后再关掉。

## 6. 端口检查

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

停止占用 8000 的进程：

```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```
