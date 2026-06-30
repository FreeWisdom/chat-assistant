# 本地微信群知识库助手产品化交付开发文档

> 先读 `LOCAL_PACKAGE_PRODUCT_ONE_PAGE.md`。本文是给 Codex/开发者执行的完整交接文档。

## 1. 产品目标

把当前仓库从“开发者运行的微信群知识库机器人”升级为“用户可本地交付的管理台产品”：

- 用户拿到一个 Windows 本地包。
- 双击启动本地服务和网页管理台。
- 在网页中完成所有运行所需配置。
- 在网页中管理知识库文档：上传、更新、删除、状态查看。
- 在网页中配置机器人、回复风格、监听群、触发词和安全开关。
- 在网页中一键启动监听、停止监听，并查看状态和日志。

FastGPT 本地知识库改造是这个目标中的“知识库 provider 子任务”，不是完整产品目标。

## 2. 当前仓库基线

已有能力：

- `backend/src/ai_ta_bot/admin_app.py`：本地 FastAPI 管理服务，提供 React 静态页面。
- `admin-ui/src/App.jsx`：管理端已支持机器人、风格、知识库、群绑定、全局配置的页面编辑。
- `backend/src/ai_ta_bot/config_store.py`：读写 `config/bot.yaml`，自动备份旧配置，并隐藏云平台内部字段。
- `backend/src/ai_ta_bot/admin/routers/knowledge.py`：百炼知识库上传、文档列表、替换、删除和 job 状态刷新。
- `backend/src/ai_ta_bot/admin/routers/runtime.py`：已有 `/api/runtime/health` 和 `/api/script/restart`。
- `backend/src/ai_ta_bot/admin/services/process_manager.py`：已有启动机器人子进程和粗粒度停止能力。
- `backend/src/ai_ta_bot/__main__.py`：机器人监听入口，包含 `LISTEN_GROUPS` 安全检查和单实例锁。

关键缺口：

- FastGPT provider 未实现。
- 运行控制只有“重启”，没有“启动/停止/状态/日志/失败原因”的完整控制面。
- `.env` 中的服务级配置仍主要靠用户手工编辑。
- 管理端还绑定百炼上传链路，未抽象为 provider 管理。
- 没有面向普通用户的本地包、启动器、依赖检查、初始化向导。

## 3. MVP 闭环

### 3.1 用户输入

- DeepSeek API Key、Base URL、模型名。
- FastGPT Base URL、API Key、Dataset/App 绑定信息。
- 微信群名白名单。
- 机器人身份、职责、回复风格、触发词。
- 知识库文档文件。

### 3.2 系统处理

- 写入 `backend/.env` 中的机器/密钥配置。
- 写入 `config/bot.yaml` 中的业务配置。
- 上传文档到当前 provider 对应的知识库。
- 维护本地 SQLite 文档/版本/任务状态。
- 启动独立机器人监听进程。
- 监听白名单微信群并按触发规则回复。

### 3.3 用户输出

- 网页看到“管理服务在线、机器人监听中/已停止、配置是否完整、知识库处理状态、最近日志”。
- 微信群中只在白名单和触发条件满足时收到回复。
- 停止监听后，不再读取和回复微信消息。

## 4. 架构边界

### 4.1 交付形态

MVP 推荐 Windows zip 包：

```text
chat-assistant-local/
├─ 启动管理台.cmd
├─ 停止全部.cmd
├─ python-runtime/              # 随包提供的独立 Python 运行时
├─ backend/
├─ admin-ui/dist/
├─ config/
├─ runtime/
├─ scripts/
└─ README-本地运行.md
```

原因：

- 微信桌面自动化依赖交互式 Windows 桌面，不适合先做 Windows Service。
- zip 包比安装器更容易调试和升级。
- 后续稳定后再考虑 NSIS/Inno Setup 安装器。

Python 运行环境在 MVP 中选择“随包提供独立运行时”，不依赖用户系统 Python。开发期可以继续用系统 Python 和 editable install，但交付包必须由 `scripts/package-local.ps1` 生成固定目录下的 `python-runtime/`，启动器只调用这个随包解释器。

打包要求：

- `python-runtime/python.exe` 可直接执行 `-m ai_ta_bot.admin_app` 和 `-m ai_ta_bot`。
- Python 依赖在打包阶段预安装完成，用户机器不运行 `pip install`。
- `admin-ui/dist` 已构建完成，用户机器不需要 Node.js 或 npm。
- 包路径允许放在中文目录和带空格目录下。
- 如果后续改用 PyInstaller 或安装器，仍必须保持同样的启动器和 API 契约。

### 4.2 运行进程

至少两个进程：

- 管理服务进程：`python -m ai_ta_bot.admin_app`
- 机器人监听进程：`python -m ai_ta_bot`

管理服务负责启动/停止机器人监听进程，但不应和机器人进程混在同一个进程里。

### 4.3 状态边界

- `backend/.env`：密钥和机器级配置，只在服务端保存，不返回完整明文。
- `config/bot.yaml`：机器人、风格、知识库、群绑定等业务配置。
- `runtime/bot_state.db`：对话历史、任务状态、文档版本状态。
- `runtime/bot.pid`：当前机器人监听进程 PID。
- `runtime/bot_health.json`：机器人心跳、监听群、DRY_RUN、最近错误。
- `runtime/logs/`：管理服务和机器人日志。

## 5. 必做模块

### 5.1 本地包启动器

新增：

```text
scripts/package-local.ps1
scripts/launcher/start-admin.cmd
scripts/launcher/stop-all.cmd
scripts/launcher/check-runtime.ps1
```

要求：

- 双击 `启动管理台.cmd` 后启动管理服务。
- 如果 8000 端口已被本产品占用，直接复用或提示。
- 如果端口被其他进程占用，给出可读错误。
- 启动成功后自动打开浏览器。
- 所有日志写入 `runtime/logs/admin_*.log`。

验收：

- 在干净目录解压后，双击启动器可打开管理页。
- 管理页静态资源由 `admin_app.py` 服务，不需要用户运行 `npm`。
- 启动失败时控制台和日志都有明确原因。

### 5.2 运行控制 API

改造：

```text
backend/src/ai_ta_bot/admin/routers/runtime.py
backend/src/ai_ta_bot/admin/services/process_manager.py
```

新增或调整 API：

```text
GET  /api/runtime/health
GET  /api/runtime/logs
POST /api/runtime/start
POST /api/runtime/stop
POST /api/runtime/restart
```

#### API 契约

`GET /api/runtime/health`

Response:

```json
{
  "ok": true,
  "status": "running",
  "running": true,
  "pid": 12345,
  "startedAt": "2026-06-29T10:15:30+08:00",
  "stoppedAt": null,
  "exitCode": null,
  "dryRun": true,
  "listenGroups": ["项目研究"],
  "botMentionNames": ["副业助手"],
  "lastHeartbeatAt": "2026-06-29T10:16:05+08:00",
  "lastError": "",
  "logFile": "runtime/logs/bot_20260629_101530.log",
  "warnings": [
    {
      "code": "WECHAT_NOT_VERIFIED",
      "message": "尚未确认桌面微信窗口可用"
    }
  ]
}
```

字段约束：

- `status` 只允许 `not_started`、`starting`、`running`、`stopping`、`stopped`、`exited`、`error`。
- `running` 是给前端按钮使用的布尔快捷字段。
- `pid` 不存在时为 `null`。
- 时间字段统一 ISO 8601 字符串，不存在时为 `null`。

`GET /api/runtime/logs?limit=200`

Response:

```json
{
  "ok": true,
  "logFile": "runtime/logs/bot_20260629_101530.log",
  "lines": [
    "10:15:30 [INFO] main: AI 助教机器人 启动中..."
  ],
  "truncated": false
}
```

MVP 用轮询读取最近 N 行，不做 WebSocket。`limit` 默认 200，最大 1000。

`POST /api/runtime/start`

Request:

```json
{
  "force": false
}
```

Response:

```json
{
  "ok": true,
  "status": "starting",
  "pid": 12345,
  "logFile": "runtime/logs/bot_20260629_101530.log",
  "blockingChecks": [],
  "warnings": []
}
```

`force=false` 时，如果已有本产品启动的机器人进程正在运行，返回当前进程状态，不重复启动。`force=true` 只允许执行“先停止再启动”，不能跳过 blocking checks。

`POST /api/runtime/stop`

Request:

```json
{
  "force": false,
  "timeoutSeconds": 8
}
```

Response:

```json
{
  "ok": true,
  "status": "stopped",
  "stoppedPids": [12345],
  "message": "机器人监听已停止"
}
```

`force=false` 先尝试温和停止；超时后返回 `status=error` 和可读错误。`force=true` 才允许 `taskkill /F`，且只能杀 PID 文件指向并通过命令行校验的本产品进程。

`POST /api/runtime/restart`

Request:

```json
{
  "force": false
}
```

Response 与 `start` 相同，额外包含：

```json
{
  "stoppedPids": [12345]
}
```

实现要求：

- 用 PID 文件和进程探测管理机器人进程，不依赖模糊扫描所有 `python.exe`。
- `start` 前做配置校验，按下方 blocking/warning 门禁执行。
- `stop` 只停止本产品启动的机器人进程，不杀管理服务。
- `restart` = stop + start。
- `health` 返回：是否运行、PID、启动时间、DRY_RUN、监听群、最近错误、最近心跳时间。
- `logs` 返回最近 N 行日志，前端可查看。

#### 启动门禁

Blocking checks，失败就拒绝启动：

- `backend/.env` 可读取，且没有解析错误。
- `config/bot.yaml` 可读取，且 `config_store.validate_config()` 无错误。
- `LLM_API_KEY` 已配置。MVP 主线仍由本项目调用 DeepSeek 生成最终回复。
- `REQUIRE_LISTEN_GROUPS=true` 时，`LISTEN_GROUPS` 至少有一个群。
- `LISTEN_GROUPS` 中每个群都存在于 `bindings[]`。
- 每个被监听群至少绑定一个存在的机器人和知识库。
- 被监听群绑定的知识库 provider 均受支持，且同一群内 MVP 阶段不能混用 provider。
- `DRY_RUN=false` 时必须二次确认：页面保存过“允许真实发送”的确认状态；没有确认则拒绝启动。
- 已有机器人进程运行且不是本产品 PID 文件记录的进程时，拒绝启动并提示人工检查。

Warnings，只提示但不阻止启动：

- 尚未确认桌面微信窗口可用。
- `BOT_MENTION_NAMES` 为空，此时只能依赖触发词，`@机器人` 和引用识别可能不准。
- `WEB_SEARCH_ENABLED=true` 但搜索 provider API Key 未配置，联网兜底不可用。
- FastGPT 连接测试失败，但当前监听群未绑定 FastGPT provider。
- 知识库文档仍在 `PROCESSING`，可能暂时检索不到新资料。

`POST /api/runtime/start` 返回的 `blockingChecks` 和 `warnings` 都使用统一结构：

```json
{
  "code": "MISSING_LLM_API_KEY",
  "level": "blocking",
  "message": "缺少 LLM_API_KEY，无法启动回答生成"
}
```

验收：

- 页面可一键启动监听。
- 页面可一键停止监听。
- 停止后微信群不再读取/回复。
- 重复点击启动不会产生多个机器人监听进程。
- 机器人异常退出后页面显示“已停止/异常退出”和最近错误。

### 5.3 网页配置闭环

现有 `config_store.py` 负责 `bot.yaml`。还需要新增 `.env` 的安全配置层：

```text
backend/src/ai_ta_bot/env_store.py
backend/src/ai_ta_bot/admin/routers/settings.py
```

配置分组：

- 模型配置：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- FastGPT 配置：`FASTGPT_BASE_URL`、`FASTGPT_API_KEY`、timeout/default top K/min score。
- 微信安全配置：`DRY_RUN`、`LISTEN_GROUPS`、`BOT_MENTION_NAMES`、`REQUIRE_LISTEN_GROUPS`。
- 联网搜索配置：`WEB_SEARCH_ENABLED`、provider、API Key。
- 管理台安全配置：`ADMIN_SYNC_TOKEN`、CORS。

安全要求：

- API Key 页面只显示“已配置/未配置”和尾号，不回显完整明文。
- 空提交表示不修改原密钥。
- 明确的“清空密钥”动作才允许删除。
- 保存前做格式校验和依赖提示。

验收：

- 用户不打开文件也能完成首次配置。
- 保存后重启机器人可读取新配置。
- 浏览器接口不泄露完整 API Key。

### 5.4 知识库 provider 抽象与 FastGPT

按 `FASTGPT_LOCAL_KB_MIGRATION_HANDOFF.md` 执行，但必须纳入产品目标：

- `aliyun_bailian` 作为兼容回滚路径。
- `fastgpt` 作为目标本地/私有化知识库 provider。
- 管理端上传、替换、删除必须按 provider 分派。
- 文档生命周期继续放在 SQLite，不把版本历史塞进 `bot.yaml`。

FastGPT MVP 优先级：

1. `search_test` 检索闭环。
2. 文档上传代理。
3. 替换/删除文档。
4. App 对话 fallback。

验收：

- 不配置百炼 AccessKey 也能使用 FastGPT 知识库问答。
- 网页可上传文档，处理完成后可被检索。
- 替换失败时旧版本仍可用。
- 删除只删除目标知识库文档，不影响其他群。

### 5.5 前端管理台

改造 `admin-ui/src/App.jsx` 和相关组件：

- 侧边栏按钮从“重启脚本”改为“启动监听 / 停止监听 / 重启监听”。
- 首页运行状态从静态展示改为真实 `/api/runtime/health`。
- 增加日志抽屉或日志面板。
- 增加“首次配置向导”：模型 -> 知识库 -> 机器人 -> 群绑定 -> 启动监听。
- 知识库页面显示 provider：FastGPT/百炼。
- 全局设置页增加 `.env` 安全配置。

验收：

- 用户只靠网页能完成配置。
- 用户能明确看到当前是否会真实发送：`DRY_RUN=true/false`。
- 启动监听前，如果配置不完整，页面给出具体缺项。

#### 组件树与数据流

推荐拆分：

```text
App
├─ SideRail
│  ├─ RuntimeControls
│  └─ SyncStatusCard
├─ HomePage
│  ├─ RuntimeStatusPanel
│  ├─ ConfigCompletenessPanel
│  ├─ RecentLogsPanel
│  └─ FirstRunChecklist
├─ SettingsPage
│  ├─ ModelSettingsForm
│  ├─ FastGPTSettingsForm
│  ├─ WeChatSafetyForm
│  └─ SearchSettingsForm
├─ BotProfilesPage
├─ StylesPage
├─ KnowledgeWorkspace
├─ BindingsPage
├─ RuntimeLogDrawer
└─ FirstRunWizard
```

状态管理：

- MVP 继续使用 React `useState/useEffect`，不引入 Redux/Zustand。
- `config` 保存 `GET /api/config` 的业务配置。
- `settings` 保存 `.env` 安全配置摘要。
- `runtime` 保存 `GET /api/runtime/health`。
- `logs` 由日志抽屉打开后按需拉取。

轮询策略：

- 管理页加载后每 3 秒轮询 `/api/runtime/health`。
- 机器人 `status=starting` 或 `stopping` 时改为每 1 秒轮询，最多 30 秒。
- 日志抽屉打开时每 2 秒轮询 `/api/runtime/logs?limit=300`；关闭后停止日志轮询。
- 知识库 job 状态沿用现有手动刷新/处理中自动刷新机制，不和 runtime 轮询混在一起。

首次配置向导：

- MVP 使用全屏向导页或右侧 drawer 均可，但必须是多步流程，不要塞进单个长表单。
- 步骤固定为：模型配置 -> 知识库连接 -> 机器人身份/风格 -> 群绑定/触发词 -> 安全确认/启动监听。
- 每步保存后可退出；已完成状态来自后端配置完整度 API，不只依赖前端本地状态。

日志面板：

- MVP 使用 HTTP 轮询，不做 WebSocket。
- 只展示本产品日志文件尾部内容。
- 日志中需要在后端过滤明显密钥片段，例如 `sk-...`、`Bearer ...`。

## 6. 开发阶段

### 阶段 1：本地管理台产品化

目标：不动 FastGPT，先把“网页控制机器人进程”做扎实。

任务：

- 完成 start/stop/restart runtime API。
- 增加 PID 文件、健康状态、日志读取。
- 前端接入真实运行状态。
- 启动器双击打开管理页。

验收：

- 管理页能启动、停止当前百炼版机器人。
- `DRY_RUN=true` 下可安全验证。
- `scripts/self-test.ps1` 通过。

### 阶段 2：配置全量网页化

目标：用户不编辑 `.env` 和 `bot.yaml` 也能配置完整。

任务：

- 新增 `env_store.py`。
- 前端增加模型/FastGPT/微信安全/联网搜索设置。
- 保存时保留密钥，避免误清空。
- 增加配置完整度检查 API。

验收：

- 新目录初始化后，用户能从网页完成首次配置。
- API Key 不完整回显。
- 重启后配置生效。

### 阶段 3：FastGPT 知识库主线

目标：把知识库从百炼切到 FastGPT。

任务：

- 实现 provider protocol、factory、FastGPT client。
- FastGPT 检索结果标准化。
- 管理端 provider 配置和连接测试。
- 文档上传/替换/删除接 FastGPT。

验收：

- FastGPT 可独立跑通，无百炼依赖。
- 微信问题命中 FastGPT Dataset 并回复。
- 文档版本安全策略通过测试。

### 阶段 4：本地包交付

目标：形成可发给用户的包。

任务：

- `scripts/package-local.ps1` 生成交付目录。
- 包内包含构建后的 `admin-ui/dist`。
- 包内包含启动器和停止器。
- 首次运行创建 `runtime/`、`.env`、默认 `bot.yaml`。
- 输出 `README-本地运行.md`。

验收：

- 在新目录解压后能启动管理台。
- 管理台能完成配置、上传文档、启动监听、停止监听。
- 不需要用户运行 `npm`。
- 用户不需要安装系统 Python；启动器使用包内 `python-runtime/python.exe`。

### 阶段依赖关系

严格串行：

- 阶段 1 必须先完成。后续所有功能都依赖可靠的运行控制、日志和健康状态。
- 阶段 2 必须在阶段 4 前完成。否则用户仍要手工编辑 `.env`，不满足本地包交付目标。

可并行：

- 阶段 2 后半段和阶段 3 可以并行，但要先冻结共享字段：`FASTGPT_BASE_URL`、`FASTGPT_API_KEY`、`fastgptMode`、`fastgptDatasetIds`、`fastgptAppId`、`retrievalTopK`、`minScore`。
- 前端设置页和 FastGPT adapter 可以并行，但所有密钥字段必须走 `env_store.py` 的隐藏/保留语义。

共享改动协调点：

- `config_store.py`：阶段 2 和阶段 3 都会改，先合入 provider 字段保留和校验，再做 UI。
- `admin/routers/knowledge.py`：阶段 3 才做 provider 分派；阶段 2 不改上传语义。
- `admin-ui/src/App.jsx`：阶段 1 先拆 RuntimeControls；阶段 2 再加 SettingsPage；阶段 3 再改 KnowledgeWorkspace provider UI。
- `backend/.env.example`：阶段 2 统一新增服务级配置，阶段 3 只补 FastGPT 注释，不重复定义。

## 7. 测试计划

后端测试：

- `test_runtime_process_manager.py`
- `test_runtime_router.py`
- `test_env_store.py`
- `test_fastgpt_knowledge.py`
- `test_fastgpt_config_store.py`
- `test_package_layout.py`

前端验证：

- `npm run build`
- 手动验证运行状态轮询。
- 手动验证启动/停止按钮状态。
- 手动验证密钥字段不会回显完整值。

端到端验收：

- `DRY_RUN=true`：真实微信消息触发后只生成拟回复，不发送。
- `DRY_RUN=false`：只监听 `LISTEN_GROUPS` 中配置的群。
- 停止监听后不再产生新回复。
- FastGPT 服务不可用时任务失败并提示，不编造答案。

## 8. 风险与处理

### 微信自动化必须运行在交互式桌面

不要把机器人监听做成 Windows Service 的第一版。服务会遇到桌面会话和 UI 自动化权限问题。MVP 用双击启动器和常驻控制台/后台进程更稳。

### 进程停止不能误杀

当前 `stop_bot()` 是按命令行扫描 Python 进程。产品化版本必须改为 PID 文件 + 命令行校验 + 健康文件，避免杀掉用户其他 Python 程序。

### 密钥不能泄露到浏览器

所有 API Key 只能显示配置状态或尾号。配置保存接口要支持“不修改原密钥”和“明确清空密钥”两种语义。

### FastGPT 比普通脚本重

如果客户电脑配置不够，FastGPT 应部署在局域网服务器，本地包只运行微信监听和管理台。网页配置 `FASTGPT_BASE_URL` 指向该服务。

## 9. 完成定义

这个产品目标完成的标准不是“FastGPT 接上了”，而是：

- 用户拿到包后不用改代码。
- 用户能从网页完成所有必要配置。
- 用户能从网页管理知识库文档。
- 用户能从网页启动和停止监听。
- 机器人只在白名单群、触发条件满足时回复。
- 所有密钥和内部平台 ID 不泄露给浏览器。
- 异常时页面能告诉用户哪里没配好或哪个服务不可用。
