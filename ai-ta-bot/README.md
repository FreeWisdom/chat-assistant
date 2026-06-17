# AI 社群助教

这是一个本地运行的微信社群知识库助教。主链路是：读取指定微信群消息，按群绑定选择机器人、回复风格和知识库，检索本地资料，调用 DeepSeek/OpenAI 兼容接口生成短回复，再通过 `wxauto4` 发送到群里。

## 主链路

1. `main.py` 加载环境变量、机器人配置和知识库。
2. `course_manager.py` 读取 `config/courses.yaml`，建立 群 -> 机器人/风格/知识库 的运行时配置。
3. `rag_engine.py` 只在当前群绑定的知识库中检索资料，并按机器人风格组装 prompt。
4. `message_analyzer.py` 判断消息是否像问题，并处理冷却时间。
5. `wechat_bot.py` 使用 `wxauto4` 轮询指定微信群，读取新消息并按正常阅读/输入节奏发送回复。

## 运行方式

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
copy .env.example .env
python -m pip install -r requirements.txt
python admin_app.py
```

打开本地管理页：

```text
http://127.0.0.1:8000
```

本地管理页主要用于本机调试和兜底编辑。页面已改为根目录 `admin-ui` 下的 React 管理端；执行 `npm run build` 后，`admin_app.py` 会优先服务 `admin-ui/dist`。

React 管理端开发模式：

```powershell
cd d:\git_hub\chat-assistant\admin-ui
npm install
npm run dev
```

Vite 开发服务会把 `/api` 代理到 `http://127.0.0.1:8000`。

正式流程可以是：用户先在平台填写机器人身份、回复风格、知识库和群绑定，平台保存后调用本机同步接口，把配置和知识库文件写入本地项目。同步完成后，重启机器人进程才会生效。

机器人运行：

```powershell
python main.py
```

运行前需要确认：

- Windows 桌面版微信已登录，且版本保持当前可用版本。
- `.env` 里已填写 `LLM_API_KEY`。
- `config/courses.yaml` 里的 `bindings.group` 和微信会话名称一致。
- 知识库文件放在 `knowledgeBases.path` 指向的目录中。

## 配置结构

`config/courses.yaml` 已升级为 v2 结构。本地管理页和平台同步接口都会写入同一份配置，并在 `config/backups/` 中备份旧配置。

- `botProfiles`：机器人身份、职责和回答策略。
- `styles`：回复语气、长度、禁用表达和示例话术。
- `knowledgeBases`：知识库名称、路径、标签、优先级和未命中策略。
- `bindings`：微信群和机器人、知识库、触发词的绑定关系。

这样用户改“说话风格”不会误伤知识库，新增知识库也只需要调整群绑定里的 `knowledgeBaseIds`。

## 平台同步流程

本地项目启动同步服务：

```powershell
python admin_app.py
```

平台保存配置后，调用本机接口：

```text
POST http://127.0.0.1:8000/api/sync/apply
Header: X-Admin-Token: <ADMIN_SYNC_TOKEN>
Body: {
  "config": {
    "botProfiles": [],
    "styles": [],
    "knowledgeBases": [],
    "bindings": [],
    "global": {}
  }
}
```

平台上传知识库文件到本地：

```text
POST http://127.0.0.1:8000/api/sync/knowledge/upload
Header: X-Admin-Token: <ADMIN_SYNC_TOKEN>
FormData:
  kb_id=<knowledgeBase id>
  file=<md/txt/json 文件>
```

平台可以先探测本机同步服务是否可用：

```text
GET http://127.0.0.1:8000/api/sync/health
Header: X-Admin-Token: <ADMIN_SYNC_TOKEN>
```

如果平台前端要直接从浏览器同步到本机，需要把平台域名加入 `.env` 的 `ADMIN_CORS_ORIGINS`。如果由平台后端同步，需要确保平台后端能访问这台机器的同步服务；普通公网平台通常无法直接访问用户本机 `127.0.0.1`，这种场景更适合让平台前端在用户浏览器里调用本机同步接口。

## 环境变量

在 `.env` 中可以调整这些参数：

- `POLL_INTERVAL=12`：每轮检查完所有群后等待多少秒。
- `POLL_LOAD_WAIT=3`：切换到某个群后等待微信消息区加载多少秒。
- `CHAT_SEARCH_TIMEOUT=5`：用微信搜索框定位会话时最多等待多少秒。
- `FORCE_SWITCH_EACH_POLL=false`：是否每一轮都强制重新搜索切换会话。
- `COOLDOWN_SECONDS=30`：同一个人在同一个群里触发回复后的冷却时间。
- `MAX_REPLY_LENGTH=500`：超过该长度时分段发送。
- `REPLY_DELAY_MIN=1.0` / `REPLY_DELAY_MAX=4.0`：回复前的随机等待时间，用来模拟正常阅读和输入节奏。
- `ADMIN_SYNC_TOKEN`：平台同步接口 token。正式使用建议填写随机值。
- `ADMIN_CORS_ORIGINS`：允许直接调用本机同步服务的平台前端域名，多个域名用英文逗号分隔。

## 当前边界

- 知识库检索仍是本地关键词检索，还没有接入向量检索。
- 还没有长期用户记忆；当前只保留群内最近上下文。
- 本地管理页默认监听 `127.0.0.1:8000`，不要直接暴露到公网。
