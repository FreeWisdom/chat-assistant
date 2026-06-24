# AI 社群助教机器人

微信群云知识库问答机器人。支持 `#举手 问题`、`@机器人 问题`，以及引用
机器人消息后继续提问，统一基于 DeepSeek、阿里云百炼知识库和按需联网搜索生成回答。

## 目录结构

```
chat-assistant/
├── admin-ui/                  # React 管理前端（唯一前端，Vite 构建）
│   ├── src/                   # 源码
│   ├── dist/                  # 构建产物（admin_app.py 直接服务此目录）
│   └── vite.config.js         # 开发时 /api 代理到 127.0.0.1:8000
│
├── backend/                   # Python 后端（正式包，可 pip install -e .）
│   ├── src/ai_ta_bot/
│   │   ├── __main__.py              # 机器人入口 → python -m ai_ta_bot
│   │   ├── admin_app.py             # 管理页入口 → python -m ai_ta_bot.admin_app
│   │   ├── config.py                # 环境配置读取（.env → Python）
│   │   ├── config_store.py          # 配置持久化（读写 config/bot.yaml）
│   │   ├── admin/                   # 管理端 API 模块
│   │   │   ├── routers/config.py    #   配置 CRUD + 同步
│   │   │   ├── routers/knowledge.py #   百炼文档上传、建库和任务状态
│   │   │   ├── routers/runtime.py   #   进程重启
│   │   │   └── services/process_manager.py
│   │   ├── application/             # 应用层：编排启动、问答流程
│   │   ├── configuration/           # 配置模型与 YAML 加载
│   │   ├── domain/                  # 领域逻辑：触发策略
│   │   ├── integrations/            # 微信 wxauto4 适配
│   │   ├── knowledge/               # 百炼检索、问题路由、联网搜索、LLM 生成
│   │   └── persistence/             # SQLite 会话与任务状态
│   ├── tests/                       # 单元测试
│   ├── pyproject.toml               # 包依赖声明
│   └── .env                         # 密钥和机器环境（不入 git）
│
├── config/
│   └── bot.yaml                     # 业务配置：群绑定、机器人、知识库、风格
│
├── runtime/                         # 运行数据（不入 git）
│   ├── bot_state.db                 #   任务去重 + 用户对话历史
│   ├── logs/                        #   微信日志 + 重启日志
│   └── backups/                     #   bot.yaml 自动备份
│
├── scripts/
│   ├── check-environment.ps1        # 环境检查
│   ├── start-bot.ps1                # 启动机器人
│   └── start-admin.ps1              # 启动管理页
│
└── README.md                        # 本文件
```

## 快速开始

### 1. 环境检查

```powershell
.\scripts\check-environment.ps1
```

同步微信自动化依赖到 `FreeWisdom/wxauto-4.0` 的远端 `main` 最新提交，并验证实际导入版本：

```powershell
.\scripts\sync-wxauto4.ps1
```

脚本会读取远端最新提交 SHA，同步项目内全部版本声明，重新安装完整的
`wxauto4` 包，并拒绝本机其他 editable checkout 覆盖项目锁定版本。

### 2. 安装依赖

```powershell
cd backend
pip install -e .
```

### 3. 配置

**backend/.env** — 密钥和机器环境：

```ini
LLM_API_KEY=sk-your-deepseek-key
ALIBABA_CLOUD_ACCESS_KEY_ID=your-access-key-id
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_BAILIAN_WORKSPACE_ID=llm-xxxxxxxx
DRY_RUN=true
LISTEN_GROUPS=项目研究,每日饮食打卡🍽️
REQUIRE_LISTEN_GROUPS=true
WEB_SEARCH_ENABLED=true
TAVILY_API_KEY=tvly-your-key
```

**config/bot.yaml** — 群、机器人、知识库绑定：

```yaml
botProfiles:
  - id: my-bot
    name: 我的机器人
    ...
knowledgeBases:
  - id: my-kb
    name: 我的百炼知识库
    provider: aliyun_bailian
    workspaceId: llm-xxxxxxxx
    indexId: xxxxxxxx
bindings:
  - group: 项目研究
    botId: my-bot
    knowledgeBaseIds: [my-kb]
    replyTriggers: ["#举手"]
```

通过管理页 `http://127.0.0.1:8000` 也可以图形化编辑。云服务凭证、
Workspace、Index 和任务 ID 都由平台后端管理，不返回用户浏览器。用户新建
知识库时只需填写名称并选择文档；后端会依次申请
上传租约、把文件直接传给百炼、等待文件解析、创建知识库并提交索引任务。
已有知识库时，同一个入口会把新文档追加到原知识库。页面可刷新查看
处理状态，生成的 `Index ID`、`Job ID` 和文档 ID 只会写回服务端
`config/bot.yaml`，项目不会长期保存用户上传的文件。

管理页同时提供文档列表、版本历史、替换和删除：

- 新增文档会建立独立的逻辑文档记录和第一个版本。
- 替换文档会先上传并索引新版本；只有新版本成功后才移除旧版本。
- 新版本失败时继续保留旧版本，避免机器人突然失去原有资料。
- 删除文档会从知识库移除当前版本，并保留本地版本操作记录。
- 云端文件 ID、任务 ID 和校验值只存服务端 SQLite，不返回浏览器。

RAM 授权、业务空间成员关系和平台 Workspace 只需由运营方初始化一次。之后
每个用户上传文档时，后端在统一业务空间中为其创建独立知识库，无需用户注册
阿里云账号或重复配置云端权限。

支持的文档类型：`doc`、`docx`、`wps`、`ppt`、`pptx`、`xls`、`xlsx`、
`md`、`txt`、`pdf`、`epub`、`mobi`。默认单次最多 10 个文件、每个文件
最大 100 MB，可通过 `backend/.env` 中的 `KNOWLEDGE_UPLOAD_*` 配置调整。

回答前先由 DeepSeek 做问题路由：稳定通用问题直接回答；依赖群资料的问题
通过阿里云百炼 Retrieve API 检索当前群绑定的云知识库；需要天气、新闻、
价格、最新进展等实时外部事实时，才调用配置的火山引擎或 Tavily 搜索。
云知识库未命中时，联网搜索作为最后
兜底。所有路径最终都由 DeepSeek 统一整理成自然的微信群回复。联网回答会
追加最多两个经过相关性过滤的来源 URL。

联网路由会区分“今天晚上吃什么”这类生活建议和“今天杭州天气”这类实时
事实，避免只因出现“今天”就搜索。时效问题没有相关结果时会明确说明无法
核验，不会引用无关网页冒充答案。

不启动微信的真实 API 冒烟测试：

```powershell
python scripts/smoke-answer-chain.py `
  --group "每日饮食打卡🍽️" `
  --question "最近有哪些适合上班族的高蛋白早餐建议？" `
  --force-web
```

该命令会实际消耗当前搜索提供方和 DeepSeek API 额度，但不会读取或发送微信消息。

### 4. 启动管理页

```powershell
# 先构建前端
cd admin-ui
npm install
npm run build

# 启动管理 API + 页面
python -m ai_ta_bot.admin_app
# 打开 http://127.0.0.1:8000
```

### 5. 启动机器人

```powershell
# 确保桌面微信已登录
python -m ai_ta_bot
```

## 关键设计决策

| 维度 | 选择 | 原因 |
|------|------|------|
| 配置 | `config/bot.yaml` + `backend/.env` | 业务配置与密钥分离；YAML 不做敏感信息 |
| 知识库 | 阿里云百炼文件/索引/Retrieve API | 页面负责发起上传和建库，文档解析、切片、向量和索引生命周期由云服务负责 |
| 运行时 | `runtime/` 独立目录 | SQLite、日志、索引不与源码混合 |
| 前端 | 仅 admin-ui（React） | 删除旧 static/ templates/，单一前端 |
| 包名 | `ai_ta_bot`（下划线） | 合法 Python 包名，支持 `python -m` |
| 微信 | 同步远端 main 后固定精确提交 | 获得完整上游功能，同时保持安装可复现 |

## 开发

```powershell
# 管理页开发（热更新）
# 终端 1
python -m ai_ta_bot.admin_app

# 终端 2
cd admin-ui && npm run dev
# 打开 http://127.0.0.1:5173

# 运行测试
.\scripts\self-test.ps1
```

只运行后端测试、跳过前端构建：

```powershell
.\scripts\self-test.ps1 -SkipFrontend
```

额外检查 wxauto4 锁定提交是否仍等于上游 `main`：

```powershell
.\scripts\self-test.ps1 -CheckUpstream
```

## 两群真实监听测试

桌面微信已登录后执行：

```powershell
.\scripts\start-two-group-test.cmd
```

启动器会硬校验白名单仅为“项目研究”和“每日饮食打卡🍽️”。两个群分别注册监听子窗口，
不同群并行处理，同一群按顺序处理；按 `Ctrl+C` 可立即停止。运行状态写入
`runtime/bot_health.json`，管理端可通过 `GET /api/runtime/health` 查询。
