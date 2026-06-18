# 微信群知识库机器人 MVP 实施交接

> 阅读顺序：先看 `MVP_CONVERGENCE_ONE_PAGE.md`。本文用于直接实施和验收。
>
> 2026-06-18 实施说明：本文保留原始验收目标。实际落地采用
> `application/ + configuration/ + domain/ + integrations/ + knowledge/ + persistence/`
> 分层结构；微信操作唯一依赖为
> `FreeWisdom/wxauto-4.0@bd7c5233e79c0a185638a325bf6d30607244dfa8`。

## 1. 目标

在当前 Windows + 微信 4.x + wxauto4 环境中，交付一个单群可灰度的知识库问答机器人：

```text
微信群消息
  -> 严格识别 #举手
  -> 提取干净问题
  -> 检索当前群绑定的本地知识库
  -> 加载该用户持久化历史
  -> DeepSeek 生成短回复
  -> DRY_RUN 或白名单群发送
  -> 持久化处理结果
```

本次收敛优先级是：正确性 > 防误发 > 可恢复 > 性能 > 管理体验。

## 2. MVP 范围

### 必须实现

- 单个白名单微信群监听。
- 仅 `#举手` 触发，可选兼容 `＃举手`。
- 本地 `.md`、`.txt`、`.json` 知识库。
- 轻量关键词/FAQ 检索。
- 明确的检索命中阈值和未命中路径。
- 按“群 + 发送者”隔离的持久化历史。
- 持久化消息去重。
- LLM 超时、重试和启动配置校验。
- `DRY_RUN` 验收后才能打开真实发送。

### 明确不做

- WebConnector。
- Chroma 和 Sentence Transformers 作为 MVP 默认依赖。
- 多群并发稳定性承诺。
- 平台同步接口。
- 长期用户画像、偏好自动抽取、向量化记忆。
- 知识库在线编辑。
- 自动部署、自动升级和公网管理端。

## 3. 关键设计决策

### 3.1 触发规则

只在消息去除前后空格后，以 `#举手` 或 `＃举手` 开头时触发。

示例：

| 输入 | 是否触发 | 传给 RAG 的问题 |
|---|---:|---|
| `#举手 副业多久能赚钱？` | 是 | `副业多久能赚钱？` |
| `＃举手副业多久能赚钱？` | 是 | `副业多久能赚钱？` |
| `今天怎么赚钱？` | 否 | - |
| `聊天里提到了#举手这个词` | 否 | - |

暂时关闭通用问号、关键词和智能问句检测，避免误回群聊。

### 3.2 检索策略

MVP 默认：

```env
VECTOR_SEARCH_ENABLED=false
```

关键词检索规则：

- 文档 `priority` 只能用于已命中结果的排序，不能制造命中。
- 至少存在一个查询词命中正文、标题、标签或 FAQ 问题，结果才有效。
- 返回 `match_terms`、`keyword_score`、`source` 和 `chunk_id`。
- 最高结果低于阈值时返回空结果。
- 空结果必须进入澄清路径，不向 LLM 注入无关知识片段。

建议先用一组固定问题调整阈值，不在首版引入 reranker。

### 3.3 MVP 记忆

首版“长期记忆”定义为：重启后仍可读取该用户最近的有效问答，不做自动人格画像。

使用 SQLite，建议文件：

```text
ai-ta-bot/data/bot_state.db
```

表结构：

```sql
CREATE TABLE conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_name TEXT NOT NULL,
  sender_key TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_conversations_user
ON conversations(group_name, sender_key, id DESC);

CREATE TABLE processed_messages (
  message_key TEXT PRIMARY KEY,
  group_name TEXT NOT NULL,
  sender_key TEXT,
  content_hash TEXT NOT NULL,
  processed_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE INDEX idx_processed_messages_time
ON processed_messages(processed_at);
```

每次回答前读取当前“群 + 发送者”的最近 6 条问答。只保存触发后的有效问答，不保存群里全部聊天。

`sender_key` 优先使用 wxauto4 提供的稳定发送者信息。若只能拿到 OCR 昵称，则使用规范化后的群昵称，并在日志中标记 `sender_source=ocr`。

### 3.4 消息去重

优先级：

1. wxauto4 的稳定消息 ID、hash 或 runtime ID。
2. 若不存在，使用“群 + 发送者 + 内容 + 可获得的消息时间”。
3. 最差回退使用内容指纹，但只在有限时间窗口内去重，不能永久屏蔽相同问题。

建议保留 7 天记录，每次启动清理过期项。

处理状态：

- `processing`：已接收，尚未完成。
- `answered`：已生成并完成发送或 DRY_RUN。
- `failed`：处理失败，可按策略重试。

只有 `answered` 才永久阻止同一消息再次处理。

### 3.5 回复安全

- `.env` 必须显式配置 `TEST_GROUP`。
- `TEST_GROUP` 为空时，MVP 启动直接失败，不允许默认监听全部绑定。
- 第一阶段必须 `DRY_RUN=true`。
- 真实发送时 `_send_reply` 再校验当前目标群等于 `TEST_GROUP`。
- 异常时只记日志，不自动向群发送“处理异常”消息，避免故障风暴。

## 4. 实施阶段

## Phase 1：收敛触发和检索

预计：3—4 小时。

修改文件：

- `ai-ta-bot/message_analyzer.py`
- `ai-ta-bot/retrieval.py`
- `ai-ta-bot/rag_engine.py`
- `ai-ta-bot/config.py`
- `ai-ta-bot/config/courses.yaml`
- `ai-ta-bot/.env.example`

任务：

1. 将 `#举手` 解析放在所有其他规则之前。
2. 改为严格前缀触发并删除标记。
3. MVP 配置关闭 `smartDetection`，移除通用触发词。
4. 修复关键词优先级基础分问题。
5. 增加检索阈值。
6. 默认关闭向量检索。
7. `RAGEngine` 初始化时校验 API Key。
8. LLM 请求增加 30 秒超时。

验收：

- `#举手 副业多久能赚钱？` 被识别，问题正文不含 `#举手`。
- `今天怎么赚钱？` 不触发。
- 副业问题能命中正确文件。
- 量子物理问题返回空检索结果并走澄清路径。
- 无 API Key 时启动立即失败。

## Phase 2：持久化个人上下文和去重

预计：4—5 小时。

新增文件：

- `ai-ta-bot/state_store.py`
- `ai-ta-bot/tests/test_state_store.py`

修改文件：

- `ai-ta-bot/wechat_bot.py`
- `ai-ta-bot/config.py`
- `ai-ta-bot/.gitignore`

任务：

1. 初始化 SQLite 表。
2. 增加用户历史写入和读取。
3. 将内存 `chat_history[group]` 改为数据库读取的 `group + sender` 历史。
4. 将 `_processed` 替换为数据库消息状态。
5. 提取稳定消息键。
6. 增加 7 天清理策略。
7. 失败时写入 `failed`，不发送自动错误回复。

验收：

- 用户 A 的历史不会出现在用户 B 的 prompt 中。
- 重启进程后仍能读取用户 A 的最近历史。
- 同一条消息不会回复两次。
- 用户隔一段时间再次发送相同文字，仍可被视为新消息。

## Phase 3：白名单与运行安全

预计：2—3 小时。

修改文件：

- `ai-ta-bot/main.py`
- `ai-ta-bot/wechat_bot.py`
- `ai-ta-bot/config.py`
- `ai-ta-bot/.env.example`

任务：

1. 强制要求 `TEST_GROUP`。
2. 发送前二次检查白名单。
3. 启动日志打印 `DRY_RUN`、目标群、检索模式和数据库路径。
4. 对 wxauto4 初始化错误给出明确启动失败。
5. 固定 wxauto4 来源和版本说明。

验收：

- 未配置 `TEST_GROUP` 无法启动机器人。
- 代码不能向非白名单群发送消息。
- `DRY_RUN=true` 时真实发送调用次数为 0。
- 新环境能够按文档安装到指定 wxauto4 版本或提交。

## Phase 4：端到端灰度

预计：2—4 小时观察。

先运行：

```env
DRY_RUN=true
DEV_MODE=false
TEST_GROUP=指定测试群
VECTOR_SEARCH_ENABLED=false
```

测试问题集至少包含：

1. 三个明确命中知识库的问题。
2. 三个知识库外问题。
3. 两个普通聊天消息。
4. 一个重复消息。
5. 两个用户连续提问，检查历史隔离。

通过后再设置：

```env
DRY_RUN=false
```

真实发送仅测试：

- 一个白名单群。
- 两个测试账号。
- 不超过 10 次回复。

## 5. 测试文件

新增：

```text
ai-ta-bot/tests/
  test_message_analyzer.py
  test_retrieval.py
  test_state_store.py
  test_reply_guard.py
```

关键测试：

- 严格 `#举手` 前缀。
- 标记清理。
- 无关问题零结果。
- 文档 priority 不制造命中。
- 用户历史隔离。
- 重启后状态恢复。
- 重复消息窗口。
- 非白名单发送被拒绝。

建议命令：

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
python -m pytest -q
python -m py_compile main.py wechat_bot.py state_store.py retrieval.py rag_engine.py
```

## 6. 完成定义

只有以下条件全部满足，MVP 才算完成：

- 只响应以 `#举手` 开头的文本消息。
- 知识库外问题不注入无关资料。
- 回答能够定位到实际来源文件和 chunk。
- 用户历史按群和发送者隔离。
- 重启后历史和已处理消息仍存在。
- 同一消息不重复回复。
- 白名单以外的群无法发送。
- 10 个 DRY_RUN 样例通过。
- 单群真实发送不超过 10 次的灰度测试通过。
- 有一份从空白 Windows 环境开始的可重复安装说明。

## 7. 后续版本

MVP 验收完成后再按顺序考虑：

1. 用户记忆摘要和事实提取。
2. 向量检索及相关性标定。
3. 多群稳定轮询。
4. 进程守护与日志轮转。
5. 知识库在线编辑。
6. WebConnector 和平台同步。

任何后续能力都不能绕过白名单发送和检索未命中测试。
