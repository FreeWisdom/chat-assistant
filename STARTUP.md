# 项目启动命令

项目分两部分：

- `ai-ta-bot`：Python 后端、本地管理页 API、微信群机器人脚本。
- `admin-ui`：React 管理页源码，开发时使用。

## 1. 首次安装依赖

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
python -m pip install -r requirements.txt
```

如果本机有多个 Python 版本，可以改用：

```powershell
py -3.11 -m pip install -r requirements.txt
```

## 2. 启动本地管理页

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
python admin_app.py
```

打开：

```text
http://127.0.0.1:8000
```

说明：

- `8000` 是 Python 后端服务。
- 如果 `admin-ui/dist` 存在，`8000` 会展示打包后的 React 页面。
- 这个命令不会启动微信群机器人，只是启动管理页和配置同步 API。

## 3. 启动 React 开发环境

需要开两个终端。

终端 1：启动后端 API。

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
python admin_app.py
```

终端 2：启动 React 开发页。

```powershell
cd d:\git_hub\chat-assistant\admin-ui
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

说明：

- `5173` 是 React 开发环境。
- 修改 `admin-ui/src` 后会自动刷新。
- `/api` 会代理到 `http://127.0.0.1:8000`。

## 4. 更新 8000 上的打包页面

```powershell
cd d:\git_hub\chat-assistant\admin-ui
npm run build

cd d:\git_hub\chat-assistant\ai-ta-bot
python admin_app.py
```

说明：

- `npm run build` 会生成 `admin-ui/dist`。
- 之后访问 `http://127.0.0.1:8000` 才能看到最新打包页面。

## 5. 启动微信群机器人

确认微信桌面端已登录、`.env` 里已填写 `LLM_API_KEY` 后再执行：

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
python main.py
```

如果使用 Python 3.11：

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
py -3.11 main.py
```

注意：

- `main.py` 是真正的机器人脚本，会连接微信、读取群消息，并可能发送回复。
- `main.py` 不负责启动网页。
- 网页服务由 `admin_app.py` 启动。

## 6. 查看 8000 端口是否已启动

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

如果需要停止占用 8000 的 Python 进程：

```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```
