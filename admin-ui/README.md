# 微信群聊机器人管理端

React 管理端，用列表和详情弹窗维护本地机器人配置。

## 开发

```powershell
cd d:\git_hub\chat-assistant\admin-ui
npm install
npm run dev
```

开发服务会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 构建

```powershell
npm run build
```

构建后 `ai-ta-bot/admin_app.py` 会优先服务 `admin-ui/dist/index.html`，打开 `http://127.0.0.1:8000` 即可访问新版 React 页面。
