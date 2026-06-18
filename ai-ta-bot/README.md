# AI 社群助教

这是一个本地运行的微信社群知识库助教。主链路是：读取指定微信群消息，按群绑定选择机器人、回复风格和知识库，检索本地资料，调用 DeepSeek/OpenAI 兼容接口生成短回复，再通过 `wxauto4` 发送到群里。

## 主链路

1. `main.py` 只负责装配运行依赖。
2. `configuration/` 读取 `config/courses.yaml`，建立群、机器人和知识库绑定。
3. `integrations/wechat_gateway.py` 使用 `wxauto4` 独立窗口监听，将严格以 `#举手` 开头的消息写入 SQLite 任务队列。
4. `application/bot_runner.py` 从任务队列领取消息。
5. `application/question_service.py` 读取该群、该发送者的历史，调用知识检索和回答生成。
6. `knowledge/` 加载本地资料、执行检索并调用 DeepSeek/OpenAI 兼容接口。
7. 回复成功或 `DRY_RUN` 完成后，`persistence/` 才写入用户历史。

核心目录：

```text
application/     业务用例和 worker
configuration/   配置模型与加载
domain/          #举手等领域策略
integrations/    微信接入
knowledge/       知识加载、检索、答案生成
persistence/     SQLite 用户历史
tests/           无微信副作用的单元测试
```

## 运行方式

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
copy .env.example .env
python -m pip install -r requirements.txt
python admin_app.py
```

`requirements.txt` 已把微信操作层固定为
`FreeWisdom/wxauto-4.0@bd7c5233e79c0a185638a325bf6d30607244dfa8`。
项目中不再保留另一套自写微信轮询或切群实现。

MVP 默认不安装本地向量模型。确实需要 Chroma 向量检索时再执行：

```powershell
python -m pip install -r requirements-vector.txt
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
- MVP 安全模式下必须在 `.env` 明确填写 `TEST_GROUP`。
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

- `CHAT_SEARCH_TIMEOUT=5`：用微信搜索框定位会话时最多等待多少秒。
- `TASK_WORKER_INTERVAL=0.5`：SQLite 任务 worker 空闲时的检查间隔。
- `BOT_STATE_DB=./data/bot_state.db`：wxauto4 任务状态和用户历史数据库。
- `DRY_RUN=true`：完成生成和状态流转，但不向微信发送。
- `TEST_GROUP=目标群名`：唯一允许监听和回复的测试群。
- `ADMIN_SYNC_TOKEN`：平台同步接口 token。正式使用建议填写随机值。
- `ADMIN_CORS_ORIGINS`：允许直接调用本机同步服务的平台前端域名，多个域名用英文逗号分隔。

## 当前边界

- MVP 默认关闭向量检索，优先使用轻量关键词/FAQ 检索；需要时可通过环境变量启用 Chroma。
- 用户历史按“群 + 发送者”保存到 SQLite，目前只保存最近问答，不做用户画像抽取。
- 消息任务去重和回复状态由 `wxauto4` 的 SQLite 任务队列维护。
- 当前只针对显式配置的 `TEST_GROUP` 做安全灰度。
- 本地管理页默认监听 `127.0.0.1:8000`，不要直接暴露到公网。
