# 知识库模块

机器人不再保存或处理知识库文档。

本目录只包含：

- `cloud_knowledge.py`：阿里云百炼 Retrieve API 适配器。
- `maxkb_knowledge.py`：MaxKB 应用 OpenAI 兼容接口适配器。
- `question_router.py`：决定直接回答、云知识库、联网搜索或追问。
- `web_search.py`：时效性外部事实的联网搜索。
- `answer_generator.py`：MaxKB 直接回答，或组合检索结果并交给本项目 LLM 生成自然回复。

MaxKB 路线下，知识文档的上传、切片、向量化、索引、提示词和云端模型
Key 全部由 MaxKB 控制台负责。本项目只保存 `maxkbAppId` 和 MaxKB 应用
API Key，并调用 `/chat/api/{application_id}/chat/completions` 取得最终回答。

阿里云百炼 provider 仍保留旧适配器；其 `workspaceId` 与 `indexId` 仍只写入
服务端配置，AccessKey 必须放在 `backend/.env` 或系统环境变量中。
