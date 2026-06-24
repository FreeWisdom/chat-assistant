# 知识库模块

机器人不再保存或处理知识库文档。

本目录只包含：

- `cloud_knowledge.py`：阿里云百炼 Retrieve API 适配器。
- `question_router.py`：决定直接回答、云知识库、联网搜索或追问。
- `web_search.py`：时效性外部事实的联网搜索。
- `answer_generator.py`：组合检索结果并交给 DeepSeek 生成自然回复。

知识文档的上传、切片、向量化、索引和生命周期全部由阿里云百炼负责。
`config/bot.yaml` 仅保存非敏感的 `workspaceId` 与 `indexId`；AccessKey 必须
放在 `backend/.env` 或系统环境变量中。
