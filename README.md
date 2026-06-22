# AI 社群助教机器人

微信群知识库问答机器人 — 用户发 `#举手` 触发，基于本地知识库 + DeepSeek 生成回答。

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
│   │   │   ├── routers/knowledge.py #   知识库文件上传
│   │   │   ├── routers/runtime.py   #   进程重启
│   │   │   └── services/process_manager.py
│   │   ├── application/             # 应用层：编排启动、问答流程
│   │   ├── configuration/           # 配置模型与 YAML 加载
│   │   ├── domain/                  # 领域逻辑：触发策略
│   │   ├── integrations/            # 微信 wxauto4 适配
│   │   ├── knowledge/               # 知识库：加载、切块、关键词/向量检索、LLM 生成
│   │   └── persistence/             # SQLite 会话与任务状态
│   ├── tests/                       # 单元测试
│   ├── pyproject.toml               # 包依赖声明
│   └── .env                         # 密钥和机器环境（不入 git）
│
├── config/
│   └── bot.yaml                     # 业务配置：群绑定、机器人、知识库、风格
│
├── knowledge-data/                  # 知识库数据文件（.md / .json）
│   └── fuye-projects/               #   示例：副业项目库
│
├── runtime/                         # 运行数据（不入 git）
│   ├── bot_state.db                 #   任务去重 + 用户对话历史
│   ├── vector_store/                #   Chroma 向量索引
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

如需向量检索（可选，依赖较重）：

```powershell
pip install -e ".[vector]"
```

### 3. 配置

**backend/.env** — 密钥和机器环境：

```ini
LLM_API_KEY=sk-your-deepseek-key
DRY_RUN=true          # 首次启动建议 true，只读不发送
TEST_GROUP=项目研究    # 指定测试群，留空监听全部
```

**config/bot.yaml** — 群、机器人、知识库绑定：

```yaml
botProfiles:
  - id: my-bot
    name: 我的机器人
    ...
bindings:
  - group: 微信群名
    botId: my-bot
    knowledgeBaseIds: [my-kb]
```

通过管理页 `http://127.0.0.1:8000` 也可以图形化编辑。

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
| 数据 | `knowledge-data/` 独立目录 | 数据与加载代码分离 |
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
