# AI 社群助教

这是一个本地运行的微信社群知识库助教。当前版本只保留主链路：读取指定微信群消息、用本地知识库检索相关资料、调用 DeepSeek 生成短回复、通过 `wxauto4` 发送到群里。

## 主链路

1. `main.py` 加载环境变量、课程配置和知识库。
2. `course_manager.py` 读取 `config/courses.yaml`，建立微信群和知识库的映射。
3. `rag_engine.py` 从本地 Markdown、TXT、JSON 文件中检索参考资料，并调用 LLM 生成回复。
4. `message_analyzer.py` 判断消息是否像问题，并处理冷却时间。
5. `wechat_bot.py` 使用 `wxauto4` 轮询指定微信群，读取新消息并发送回复。

## 运行方式

```powershell
cd d:\git_hub\chat-assistant\ai-ta-bot
copy .env.example .env
python -m pip install -r requirements.txt
python main.py
```

运行前需要确认：

- Windows 桌面版微信已登录，且版本保持当前可用版本。
- `.env` 里已填写 `LLM_API_KEY`。
- `config/courses.yaml` 里的群名和微信会话名称一致。
- 知识库文件放在 `knowledge/fuye-projects/` 或配置里的其他 `knowledgePath`。

## 轮询配置

在 `.env` 中可以调整这些参数：

- `POLL_INTERVAL=12`：每轮检查完所有群后等待多少秒。
- `POLL_LOAD_WAIT=3`：切换到某个群后等待微信消息区加载多少秒。
- `CHAT_SEARCH_TIMEOUT=5`：用微信搜索框定位会话时最多等待多少秒。
- `FORCE_SWITCH_EACH_POLL=false`：是否每一轮都强制重新搜索切换会话。单群测试建议保持 `false`，避免频繁打开搜索框。
- `COOLDOWN_SECONDS=30`：同一个人在同一个群里触发回复后的冷却时间。

## 当前保留范围

- 保留 `wxauto4` 轮询方案。
- 保留本地知识库检索。
- 保留 DeepSeek/OpenAI 兼容接口调用。
- 保留单机本地运行方式。

## 已移除范围

- 临时诊断脚本。
- 事件驱动监听实验代码。
- 免费 `wxauto` 兼容适配层。
- Tavily 联网搜索。
- 与当前业务无关的演示知识库。
