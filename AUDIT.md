# 项目审核问题清单

> 审核日期：2026-06-17 | 版本：MVP (606d801)

---

## 方向一：先跑一周 — 真实环境收集反馈

DRY_RUN=false 上线，在真实群里跑，让群友当 QA。痛点自然浮现，再决定改什么。

- [ ] **LLM API 调用加超时** — [rag_engine.py:81](ai-ta-bot/rag_engine.py#L81) 加 `timeout=30`，防止 API 挂起阻塞整个轮询循环（上线前必须修）
- [ ] **启动时校验 API Key** — [rag_engine.py:18](ai-ta-bot/rag_engine.py#L18) key 为空时启动就报错，不等第一次调用才挂
- [ ] **轮换泄露的 API 密钥** — [ai-ta-bot/.env](ai-ta-bot/.env) DeepSeek / Tavily 密钥在对应平台重新生成
- [ ] DRY_RUN=false，在目标群上线
- [ ] 观察并记录群友真实反馈：
  - "怎么 @ 了不回" → 触发词太死 / 提问检测漏了
  - "回答太长了" → 调 max_chars / 风格配置
  - "答非所问" → 知识库内容不对 / 检索不准（先按 [[feedback_validate_before_fix]] 跑对比脚本再改）
  - "怎么半夜也回" → 需要夜间静默（见方向二）
  - "重启后重复回同一句" → 已读状态丢了（见方向二）
- [ ] **修复 `avoid_words` 子串匹配 bug** — [rag_engine.py:171](ai-ta-bot/rag_engine.py#L171) 子串替换可能误伤正常文本
- [ ] **群名表情符号匹配验证** — [courses.yaml](ai-ta-bot/config/courses.yaml) `每日饮食打卡🍽️` 需确认 wxauto4 能否可靠匹配

## 方向二：加固稳健性 — 长期挂着不操心

适合长期挂机，不用三天两头看日志。

### 状态持久化（重启不丢已读）

- [ ] **消息指纹持久化** — [wechat_bot.py](ai-ta-bot/wechat_bot.py) `_processed` 集合写入本地文件（JSON/SQLite），重启后恢复，避免重复回复
- [ ] **`_processed` 加容量上限** — 超过 N 条自动清理旧指纹，防止文件/Memory 无限增长
- [ ] **chat_history 持久化** — 群聊上下文重启后恢复，避免重启丢对话记忆

### 崩溃自动恢复

- [ ] **主循环加 watchdog** — [main.py](ai-ta-bot/main.py) bot 进程崩溃后自动拉起（外层 while 循环 + 退避延迟）
- [ ] **重启端点加健康检查** — [admin_app.py:164](ai-ta-bot/admin_app.py#L164) 重启后等 2 秒验证进程存活再返回成功
- [ ] **`wmic` 进程管理替换** — [admin_app.py:142](ai-ta-bot/admin_app.py#L142) `wmic` 已废弃，改用 PowerShell `Get-Process` 或 PID 文件

### 日志按天切割

- [ ] **RotatingFileHandler** — 替换当前无限制的日志文件，按天切割 + 保留最近 N 天
- [ ] **`LOG_LEVEL` 环境变量生效** — [config.py](ai-ta-bot/config.py) 当前定义了但从未读取
- [ ] **wxauto_logs 也加切割** — 同样限制保留天数

### 夜间静默

- [ ] **静默时间段配置** — [courses.yaml](ai-ta-bot/config/courses.yaml) global 段加 `quietHours: [23, 7]`，该时段不回复
- [ ] **静默期消息缓存或丢弃策略** — 决定静默时段内的消息是醒来后补回还是直接跳过

### 其他稳健性

- [ ] **配置写入加文件锁** — [config_store.py](ai-ta-bot/config_store.py) 用临时文件 + rename 原子写入，避免并发读到半写状态
- [ ] **无 API Key 时同步端点默认拒绝** — [admin_app.py:39](ai-ta-bot/admin_app.py#L39) token 为空时不应放行

## 方向三：扩展知识库能力

让 bot 能回答更广范围的问题。

### WebConnector 接真实站点

- [ ] **尊重 robots.txt** — [knowledge_connectors.py](ai-ta-bot/knowledge_connectors.py) `WebConnector` 抓取前检查目标站点的 robots.txt
- [ ] **JS 渲染支持** — 当前 `requests` + `BeautifulSoup` 拿不到 SPA/动态页面内容，评估是否需要 headless browser 或 fallback 方案
- [ ] **抓取用连接池** — 改用 `requests.Session` 复用连接，多个 URL 抓取时减少握手开销
- [ ] **抓取失败重试 + 错误聚合** — 当前静默吞异常，改为重试 N 次后汇总报告失败 URL

### 知识库在线增删改

- [ ] **管理端直接编辑 md** — [admin-ui](admin-ui/) 添加知识库文件编辑器，在线编辑/预览/保存 markdown
- [ ] **管理端新增/删除知识库文件** — 支持在管理页面直接创建新 md 或删除已有文件
- [ ] **faq.json 在线编辑** — 同样支持 FAQ 问答对的增删改
- [ ] **修改后自动触发重建索引** — 知识库内容变更后，向量索引和关键词索引自动重建（提示重建进度）

### 多 KB 交叉引用

- [ ] **一个 binding 绑定多个 KB 时的结果合并策略** — [retrieval.py](ai-ta-bot/retrieval.py) 当前简单合并，需支持按 KB 优先级排序、去重、来源标注
- [ ] **跨 KB 引用链接** — 回答中引用知识来源时标注来自哪个 KB、哪个文件
- [ ] **KB 间依赖/关联定义** — [courses.yaml](ai-ta-bot/config/courses.yaml) 支持在 KB 定义中声明关联 KB，检索时连带查询

## 方向四：工程基础（择机补）

以下是从审核中发现的工程问题，不影响功能但影响长期维护效率，择机补齐。

- [ ] **零测试** — 优先给 [retrieval.py](ai-ta-bot/retrieval.py)、[config_store.py](ai-ta-bot/config_store.py)、[message_analyzer.py](ai-ta-bot/message_analyzer.py) 补单元测试
- [ ] **零 linting** — Python 加 ruff，前端加 ESLint + Prettier
- [ ] **前端 TypeScript** — 已安装未使用，加 `tsconfig.json` 逐步迁移
- [ ] **前端组件拆分** — [App.jsx](admin-ui/src/App.jsx) 1244 行单体组件拆成独立文件
- [ ] **废弃 vanilla JS 前端** — [static/admin.js](ai-ta-bot/static/admin.js) + [templates/admin.html](ai-ta-bot/templates/admin.html) 双端维护成本高
- [ ] **统一配置解析** — [config_store.py](ai-ta-bot/config_store.py) 和 [course_manager.py](ai-ta-bot/course_manager.py) 重复字段定义
- [ ] **统一错误响应格式** — 全部返回 `{"ok": bool, "data": ..., "error": ...}`
- [ ] **LLM 参数可配置化** — `temperature` / `max_tokens` 硬编码，应纳入 BotStyle 或 env
- [ ] **关键词检索加倒排索引** — 当前 O(N*M) 词频统计在大规模 KB 下性能差
- [ ] **requirements.txt 锁定版本** — 确保可复现构建
- [ ] **加 LICENSE 文件**
