# FastGPT 本地知识库改造交接文档

更新时间：2026-06-26

> 本文用于在 `feat/local-kb-wechat` 分支上把当前“本地桌面微信 + 阿里云百炼云知识库”改造成“本地桌面微信 + FastGPT 本地/私有化知识库 + DeepSeek 生成”的实现交接。

## 一屏结论

当前项目的微信通道可以继续保留：Windows 桌面微信、`wxauto4`、群白名单、`DRY_RUN`、可靠回复链路都不需要重写。

本次要替换的是知识库边界：把 `AliyunBailianKnowledgeClient`、百炼上传建库、百炼 Retrieve API，替换为 FastGPT 自部署知识库和 OpenAPI。

DeepSeek 继续作为大模型。它可以继续由本项目后端调用，也可以配置到 FastGPT 的模型代理里；MVP 推荐先让本项目保留 DeepSeek 调用，FastGPT 只负责知识库上传、切分、向量化、检索和引用。

这不是完全离线方案：知识库数据落在本地/私有化 FastGPT 服务内，但 DeepSeek API 仍是外部模型服务。若要完全离线，后续还要增加本地大模型和本地 embedding 模型。

最小闭环：部署 FastGPT -> 创建知识库和应用 -> 项目新增 `fastgpt` provider -> 微信消息命中知识库问题 -> FastGPT 检索资料 -> 本项目用 DeepSeek 生成微信群回复 -> `DRY_RUN` 验证后再真实发送。

## 决策版

- 值得做：摆脱百炼 Workspace、Index、Job、Document ID 的云平台绑定，适合卖“本地部署知识库群助手”。
- 最小验证：先只接一个微信群、一个 FastGPT 知识库、一个 FastGPT App，跑通 `#举手` 提问和 `DRY_RUN` 拟回复。
- 范围边界：本轮不改企业微信，不做完全离线大模型，不做多租户 SaaS，不承诺个人微信官方级稳定。
- 最大风险：FastGPT 的知识库检索 API 与应用对话 API边界要实测；如果检索 API 不稳定，先用 FastGPT App 对话接口完成 MVP。
- 推荐动作：先做 provider 抽象和 FastGPT 适配器，不先大拆管理后台。

## 当前项目基线

当前分支：`feat/local-kb-wechat`

当前核心链路：

```text
Windows 桌面微信
-> wxauto4 / WeChatGateway
-> BotRunner
-> QuestionService.prepare()
-> RAGEngine.answer()
-> LLMQuestionRouter
-> AliyunBailianKnowledgeClient.search()
-> DeepSeek / OpenAI-compatible Chat Completions
-> WeChatGateway.reply()
```

当前知识库限制：

- `backend/src/ai_ta_bot/knowledge/cloud_knowledge.py` 只支持 `provider = aliyun_bailian`。
- `RAGEngine.validate_knowledge_bases()` 会校验百炼 `workspaceId` 和 `indexId`。
- 管理端 `backend/src/ai_ta_bot/admin/routers/knowledge.py` 直接绑定百炼上传、索引任务、任务状态和删除接口。
- `config/bot.yaml` 中的知识库结构包含百炼字段：`workspaceId`、`indexId`、`indexJobId`、`documentIds`。
- `backend/.env.example` 包含百炼 AccessKey、Endpoint、Workspace 等配置。

当前应保留：

- `WeChatGateway` 本地微信监听和回复。
- `QuestionService` 的触发词、群绑定、历史上下文和任务状态。
- `DRY_RUN`、`LISTEN_GROUPS`、`BOT_MENTION_NAMES` 安全边界。
- DeepSeek 配置：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- SQLite 运行状态：`runtime/bot_state.db`。

## 目标架构

```text
Windows 桌面微信
-> WeChatGateway
-> BotRunner
-> QuestionService
-> RAGEngine
-> KnowledgeClient(provider=fastgpt)
-> FastGPT 本地/私有化服务
   -> 文档上传、解析、切分、向量化、检索、引用
-> DeepSeek 生成自然微信群回复
-> WeChatGateway.reply()
```

部署边界：

```text
客户电脑或客户服务器
├─ chat-assistant 后端
├─ chat-assistant 管理端
├─ runtime/bot_state.db
├─ Windows 桌面微信
└─ FastGPT Docker Compose
   ├─ FastGPT App
   ├─ MongoDB
   ├─ PostgreSQL / Milvus / 其他向量库
   ├─ 对象存储 / 本地文件存储
   └─ AIProxy / 模型配置
```

FastGPT 官方自部署文档描述的核心依赖包括 MongoDB、向量数据存储和 AIProxy。OpenAPI 支持 API Key 鉴权、应用对话、上传知识库数据和搜索测试。对话接口兼容 OpenAI SDK 风格；知识库接口支持本地文件上传到数据集。

## 关键产品边界

### 支持

- 本地桌面微信监听白名单群。
- `#举手`、`@机器人`、引用机器人消息后的继续提问。
- FastGPT 自部署知识库。
- 每个微信群绑定一个或多个 FastGPT 知识库或 FastGPT App。
- 当前 DeepSeek 作为回答生成模型。
- 管理后台配置群、机器人、知识库绑定。
- `DRY_RUN` 首次验证。
- 失败重试、回复状态、运行健康检查沿用当前项目。

### 不支持

- 不做完全离线大模型。
- 不把 DeepSeek API Key 暴露到浏览器。
- 不承诺个人微信官方接口级稳定性。
- 不在第一版实现多租户 SaaS。
- 不在第一版实现企业微信官方机器人。
- 不在第一版迁移百炼历史 Job/Document ID 到 FastGPT。
- 不在第一版实现复杂权限、团队协作和审计。

## FastGPT 集成策略

### 推荐 MVP 策略：FastGPT 负责知识库，项目负责最终回复

FastGPT 负责：

- 文档上传。
- 文档解析。
- 分段。
- 向量化。
- 检索。
- 返回命中内容和引用信息。

本项目负责：

- 微信监听。
- 群绑定。
- 是否触发回复。
- 问题路由。
- 历史上下文。
- DeepSeek 最终回答。
- 微信发送和发送后验证。

这样做的好处：

- 最大程度保留当前微信群语气、触发规则和安全边界。
- FastGPT 替代的是百炼知识库，不吞掉整个机器人业务逻辑。
- 后续仍可把同一知识库接到 Web、企业微信或其他通道。

### 备选 MVP 策略：直接调用 FastGPT App 对话接口

如果 FastGPT 的检索/搜索测试 API 在当前版本里不好稳定对接，第一版可以把 FastGPT App 当成完整 RAG 应用：

```text
QuestionService
-> FastGPT App Chat Completions
-> 返回答案
-> 微信回复
```

此时 DeepSeek 需要配置到 FastGPT 的模型代理里。本项目仍可能需要 DeepSeek 做通用问题、联网路由和回答润色，所以要避免同一问题被两边重复调用。

推荐把这个方案作为降级路径，不作为长期结构。

## 配置设计

### provider 决策边界

当前项目已经是 per-knowledge-base 配置：每个 `knowledgeBases[]` 自己声明 `provider`。不要新增全局 `KNOWLEDGE_PROVIDER`，否则会和现有 `config/bot.yaml` 的 provider 字段冲突。

规则：

- `provider` 只由 `config/bot.yaml` 中的单个知识库决定。
- 同一个群绑定多个知识库时，MVP 阶段要求这些知识库使用同一种 provider。
- FastGPT 的集成模式也放在单个知识库上，例如 `fastgptMode: search_test` 或 `fastgptMode: app_chat`，不要放全局 `FASTGPT_MODE`。
- `.env` 只保存服务级连接信息、密钥和默认检索参数。

### backend/.env 新增

```ini
# FastGPT
FASTGPT_BASE_URL=http://127.0.0.1:3000
FASTGPT_API_KEY=your_fastgpt_api_key
FASTGPT_TIMEOUT_SECONDS=30
FASTGPT_DEFAULT_TOP_K=5
FASTGPT_DEFAULT_MIN_SCORE=0.2

# DeepSeek 保持当前项目配置
LLM_API_KEY=your_deepseek_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

`FASTGPT_DEFAULT_TOP_K` 和 `FASTGPT_DEFAULT_MIN_SCORE` 是默认值，目的是和现有 `KNOWLEDGE_RETRIEVAL_MIN_SCORE` 这类全局检索默认值保持一致。若某个知识库需要不同阈值，在 `config/bot.yaml` 的单个 knowledgeBase 上用 `retrievalTopK`、`minScore` 覆盖。

注意：DeepSeek 官方文档显示 `deepseek-chat` 和 `deepseek-reasoner` 将在 2026-07-24 15:59 UTC 废弃，并且当前分别对应 `deepseek-v4-flash` 的非思考/思考模式。代码层建议同步修改 `backend/.env.example` 和 `config.py` 的默认值为 `deepseek-v4-flash`，但继续允许用户通过 `LLM_MODEL` 覆盖。

### config/bot.yaml 调整

建议保留现有 `knowledgeBases` 结构，但让 provider 可扩展：

```yaml
knowledgeBases:
  - id: fuye-projects
    name: 副业项目本地知识库
    description: 副业项目、创业思路、赚钱方法、案例分析和常见问题
    provider: fastgpt
    fastgptMode: search_test
    fastgptAppId: app_xxx
    fastgptDatasetIds:
      - dataset_xxx
    retrievalTopK: 5
    minScore: 0.2
    tags:
      - 副业
      - 赚钱
      - 项目
    priority: 10
    fallbackPolicy: clarify
    routeExamples:
      - 这个项目靠谱吗
      - 怎么做副业
bindings:
  - group: 项目研究
    botId: fuye-assistant
    knowledgeBaseIds:
      - fuye-projects
    replyTriggers:
      - "#举手"
```

以下密钥只放 `.env`，不进入 YAML 或浏览器响应：

- `FASTGPT_API_KEY`
- `LLM_API_KEY`
- 未来如有 embedding provider key，也放 `.env`

## 代码改造范围

### 1. 知识库 provider 抽象

新增：

```text
backend/src/ai_ta_bot/knowledge/provider_protocol.py
backend/src/ai_ta_bot/knowledge/fastgpt_knowledge.py
```

建议先定义返回结构，不要让 provider 之间传裸 `dict`：

```python
from typing import Any, Protocol, TypedDict


class KnowledgeSearchResult(TypedDict, total=False):
    """跨 provider 统一的检索结果。

    适配层负责把各 provider 的原始字段映射到协议字段：
      - kb_id          -> knowledge_base_id
      - kb_name / source -> source_name（预格式化的 "资料名 / 来源: xxx"）
      - _score         -> score
      - _metadata      -> metadata
    原有的 kb_name、kb_tags、priority、chunk_id、provider 等字段仍可保留，
    但不在协议中要求；新增消费代码应优先使用协议字段。
    """

    title: str
    content: str
    source_name: str           # 渲染 "资料名 / 来源: xxx"
    url: str                   # 联网搜索结果必需
    score: float
    knowledge_base_id: str
    metadata: dict[str, Any]


class KnowledgeClientProtocol(Protocol):
    provider: str

    def validate(self, knowledge_bases: list[KnowledgeBase]) -> None:
        ...

    def search(
        self,
        knowledge_bases: list[KnowledgeBase],
        query: str,
        top_k: int = 5,
    ) -> list[KnowledgeSearchResult]:
        ...
```

`RAGEngine` 不再直接写死 `AliyunBailianKnowledgeClient()`，而是通过工厂创建：

```text
provider=aliyun_bailian -> AliyunBailianKnowledgeClient
provider=fastgpt -> FastGPTKnowledgeClient
```

第一版可以要求一个运行时绑定只使用同一种 provider。不要一开始做跨 provider 混合检索。

### 2. KnowledgeBase 模型扩展

修改：

```text
backend/src/ai_ta_bot/configuration/models.py
backend/src/ai_ta_bot/configuration/loader.py
backend/src/ai_ta_bot/config_store.py
```

新增字段：

```python
fastgpt_app_id: str = ""
fastgpt_dataset_ids: list[str] = field(default_factory=list)
fastgpt_mode: str = "search_test"
retrieval_top_k: int | None = None
min_score: float | None = None
```

兼容旧字段：

- `workspaceId`
- `indexId`
- `indexJobId`
- `documentIds`

同步改动点：

- `configuration/models.py`：给 `KnowledgeBase` dataclass 增加 FastGPT 字段。
- `configuration/loader.py`：在 `_load_v2()` 构建 `KnowledgeBase(...)` 时从 YAML 读取 `fastgptAppId`、`fastgptDatasetIds`、`fastgptMode`、`retrievalTopK`、`minScore`。
- `config_store.py`：在 `normalize_config()` 中保留这些字段，否则管理端读写会丢配置。
- `config_store.py`：在 `validate_config()` 中按 provider 分支校验字段。

迁移期间不要一次性删除百炼字段。先让 `provider` 决定字段是否必填。

### 3. config_store.py 必改点

当前 `config_store.py` 不只是“需要改”，而是 FastGPT 配置能否保存和校验的关键路径，至少要改以下位置：

1. `SUPPORTED_PROVIDERS`

```python
SUPPORTED_PROVIDERS = {"aliyun_bailian", "fastgpt"}
```

2. `INTERNAL_KNOWLEDGE_FIELDS`

FastGPT 的平台内部 ID 应与百炼 `workspaceId/indexId/documentIds` 同级处理。建议加入：

```python
"fastgptAppId",
"fastgptDatasetIds",
"fastgptCollectionIds",   # 阶段 3 上传代理预留
"fastgptFileIds",         # 阶段 3 上传代理预留
```

如果第一版管理端要让用户在页面输入 App ID / Dataset ID，应使用单独的受控保存接口；普通 `public_config()` 仍不要把这些内部 ID 原样返回给浏览器。

3. `normalize_config()`

知识库标准化时增加：

```python
"fastgptMode": str(item.get("fastgptMode", "search_test") or "search_test").strip(),
"fastgptAppId": str(item.get("fastgptAppId", "") or "").strip(),
"fastgptDatasetIds": [
    str(v).strip()
    for v in _listify(item.get("fastgptDatasetIds"))
    if str(v).strip()
],
"retrievalTopK": int(item.get("retrievalTopK") or 0) or None,
"minScore": (
    float(item["minScore"])
    if item.get("minScore") not in (None, "")
    else None
),
```

4. `validate_config()`

按 provider 分支校验：

- `aliyun_bailian`：继续校验 Workspace / Index，保持现有"workspace 缺失报错、index 未完成只 warning"的语义不变。
- `fastgpt` + `search_test`：已绑定知识库必须至少有一个 `fastgptDatasetIds`。
- `fastgpt` + `app_chat`：已绑定知识库必须有 `fastgptAppId`。
- `fastgptMode` 只允许 `search_test` / `app_chat`。

5. `public_config()`

不要只用百炼字段计算 `configured`。应按 provider 返回浏览器安全状态：

```python
if provider == "fastgpt":
    configured = bool(fastgpt_app_id or fastgpt_dataset_ids)
elif provider == "aliyun_bailian":
    configured = bool(index_id)
```

可以返回 `providerLabel`、`configured`、`documentCount`、`modeLabel` 这类显示字段，但不要返回 `FASTGPT_API_KEY`、`fastgptAppId`、`fastgptDatasetIds`。

6. `merge_public_config()`

当前函数只恢复百炼后端字段。FastGPT 字段也必须从 existing 恢复，否则前端保存普通配置时会丢掉 FastGPT App/Dataset 绑定：

```python
"fastgptMode": current.get("fastgptMode", item.get("fastgptMode", "search_test")),
"fastgptAppId": current.get("fastgptAppId", ""),
"fastgptDatasetIds": current.get("fastgptDatasetIds", []),
"fastgptCollectionIds": current.get("fastgptCollectionIds", []),   # 阶段 3 上传代理预留
"fastgptFileIds": current.get("fastgptFileIds", []),               # 阶段 3 上传代理预留
```

provider 是否允许从 `aliyun_bailian` 切到 `fastgpt` 不应由普通 public config 静默完成。建议新增“知识库迁移/重绑定”专用 API，显式接收 provider 和 FastGPT 内部 ID，并写操作日志。

### 4. FastGPT 适配器

新增：

```text
backend/src/ai_ta_bot/knowledge/fastgpt_knowledge.py
```

职责：

- 从 `FASTGPT_BASE_URL`、`FASTGPT_API_KEY` 读取配置。
- 按 `fastgptMode` 校验配置：`search_test` 要有 `fastgptDatasetIds`，`app_chat` 要有 `fastgptAppId`。
- 调用 FastGPT OpenAPI。
- 把 FastGPT 返回结构标准化为当前 `RAGEngine` 能消费的引用列表。

标准化结果建议：

```python
{
    "title": "资料文件名或集合名",
    "content": "命中的知识片段",
    "source_name": "副业项目本地知识库 / 来源: 副业案例合集.pdf",
    "url": "",
    "score": 0.82,
    "knowledge_base_id": "fuye-projects",
    "metadata": {
        "datasetId": "...",
        "collectionId": "...",
        "chunkId": "..."
    }
}
```

### 5. config.py 与 RAGEngine 接入

`config.py` 需要新增 FastGPT 连接信息的读取：

```python
FASTGPT_BASE_URL = os.getenv("FASTGPT_BASE_URL", "http://127.0.0.1:3000")
FASTGPT_API_KEY = os.getenv("FASTGPT_API_KEY", "")
FASTGPT_TIMEOUT_SECONDS = float(os.getenv("FASTGPT_TIMEOUT_SECONDS", "30"))
FASTGPT_DEFAULT_TOP_K = int(os.getenv("FASTGPT_DEFAULT_TOP_K", "5"))
FASTGPT_DEFAULT_MIN_SCORE = float(os.getenv("FASTGPT_DEFAULT_MIN_SCORE", "0.2"))
```

`answer_generator.py` 的 `RAGEngine.__init__()` 当前硬编码 `AliyunBailianKnowledgeClient()`（[answer_generator.py:36-38](backend/src/ai_ta_bot/knowledge/answer_generator.py#L36-L38)），需要改为工厂模式。工厂逻辑建议放在 `knowledge/__init__.py` 或新增 `knowledge/factory.py`：

```python
def create_knowledge_client(provider: str) -> KnowledgeClientProtocol:
    if provider == "fastgpt":
        return FastGPTKnowledgeClient()
    if provider == "aliyun_bailian":
        return AliyunBailianKnowledgeClient()
    raise ValueError(f"不支持的 provider: {provider}")
```

`RAGEngine` 按群绑定的知识库 provider 选择 client。MVP 阶段要求同一个群的多个知识库使用同一种 provider，因此可以从第一个知识库的 `provider` 字段决定。

**`top_k` 优先级**（涉及 [`answer_generator.py:111`](backend/src/ai_ta_bot/knowledge/answer_generator.py#L111)）：

```
显式传参 > 单知识库 retrievalTopK > provider 全局默认值
```

- 调用方显式传 `top_k` 参数时直接使用。
- 否则取当前知识库的 `retrievalTopK`（`None` 表示未设置）。
- 仍未设置时回退到 provider 全局默认值：百炼用 `config.RETRIEVAL_TOP_K`，FastGPT 用 `config.FASTGPT_DEFAULT_TOP_K`。

这个逻辑放在 `RAGEngine.search_knowledge()` 或各 provider client 的 `search()` 中均可；推荐放在 client 内部，减少 `RAGEngine` 对 provider 差异的感知。

### 6. 管理端改造

第一版不要把 FastGPT 全量管理能力搬进本项目。推荐最小改造：

- 知识库表单显示 provider 状态：`fastgpt` / `aliyun_bailian`。
- `provider=fastgpt` 时显示安全摘要：
  - FastGPT 是否已绑定 App。
  - FastGPT Dataset 数量。
  - 当前模式：搜索测试 / App 对话。
  - 连接测试按钮
- 隐藏百炼 Workspace / Index / Job 字段。
- 隐藏 FastGPT App ID / Dataset ID 原值，除非走专用“绑定/迁移”弹窗提交。
- 文档上传第一版跳转提示用户去 FastGPT 控制台完成。
- `public_config()` 只能返回浏览器安全字段；`merge_public_config()` 必须保留后端内部 FastGPT 字段。

第二版再做 FastGPT 上传代理：

- 本项目上传文件。
- 后端调用 FastGPT Dataset localFile API。
- 本项目 SQLite 记录文档版本、FastGPT collection/file id。

### 7. 删除或降级百炼依赖

第一阶段保留：

- `cloud_knowledge.py`
- `cloud_knowledge_admin.py`
- `alibabacloud-bailian20231229`

第二阶段确认 FastGPT 跑通后再删除：

- 百炼 SDK 依赖。
- 百炼 AccessKey 环境变量。
- 百炼专用上传/任务状态接口。
- 文档中百炼默认说明。

理由：当前分支正好是百炼云知识库重构分支，直接删除会扩大风险，不利于快速验证 FastGPT。

## 最小实施顺序

### 阶段 0：本地 FastGPT 准备

1. 用 Docker Compose 部署 FastGPT。
2. 配置可用 embedding 模型。
3. 创建一个知识库 Dataset。
4. 上传一批测试文档。
5. 生成 API Key，记录 Base URL、Dataset ID。

推荐 `search_test` 模式下，FastGPT 不需要配置 DeepSeek 聊天模型，只需要可用 embedding 模型和 Dataset。只有选择 `app_chat` 备选模式时，才需要在 FastGPT 里配置 DeepSeek 聊天模型、创建 App，并记录 App ID。

注意：DeepSeek 适合做聊天生成；RAG 检索还需要 embedding 模型。若 FastGPT 当前环境没有可用 embedding 模型，需要额外配置本地或第三方 embedding 服务。

### 阶段 1：接 FastGPT 搜索测试/知识库检索，跑通主线闭环

目标：让 FastGPT 只做知识库检索，本项目继续用 DeepSeek 生成最终微信群回复。

改动：

- 新增 `FastGPTKnowledgeClient.search()`。
- `provider=fastgpt` 且 `fastgptMode=search_test` 时调用 FastGPT 搜索测试/知识库检索接口。
- `RAGEngine.search_knowledge()` 返回标准化 `KnowledgeSearchResult`。
- `RAGEngine` 继续把知识片段交给 DeepSeek 生成微信群自然回复。

验收：

- FastGPT 流程可以在不配置百炼 AccessKey 的情况下独立跑通；百炼 AccessKey 只作为 `aliyun_bailian` 回滚路径的可选配置。
- `#举手 这个项目靠谱吗` 能命中 FastGPT Dataset 并生成答案。
- `DRY_RUN=true` 时不真实发送。
- 未绑定群不调用 FastGPT。
- FastGPT client 和 `RAGEngine.search_knowledge()` 返回 `KnowledgeSearchResult` 结构（`TypedDict`，运行时仍是 `dict`），至少包含 `content`、`source_name`、`url`、`score`、`knowledge_base_id` 等协议字段。`kb_name` 等旧字段可在适配层保留，但 answer_generator 应优先消费 `source_name`。
- FastGPT 返回片段能进入当前回答 prompt。
- 回复仍保持微信群语气。

### 阶段 1B：备选 App 对话模式

目标：如果 FastGPT 搜索测试/知识库检索 API 在当前版本里不稳定，先用 App 对话接口完成端到端验证。

改动：

- 在 FastGPT 中配置 DeepSeek 聊天模型。
- 创建 FastGPT App 并绑定 Dataset。
- `provider=fastgpt` 且 `fastgptMode=app_chat` 时调用 FastGPT App 对话接口。
- 返回答案后仍走当前微信回复链路。

验收：

- `#举手` 提问可以通过 FastGPT App 返回答案。
- 不重复调用本项目 DeepSeek 生成同一个答案。
- 文档中明确标注这是临时 fallback，不是长期主线。

### 阶段 2：管理端支持 FastGPT 配置

目标：用户不用改 YAML。

改动：

- 管理端知识库表单支持 `provider=fastgpt`。
- 后端配置校验支持 FastGPT 字段。
- 增加连接测试 API。
- 页面明确显示“文档请在 FastGPT 控制台上传”。

验收：

- 新建 FastGPT 知识库配置后可保存。
- 浏览器看不到 `FASTGPT_API_KEY`。
- 配置校验能提示缺少 App ID / Dataset ID。
- 普通保存配置不会丢失已有 `fastgptAppId` / `fastgptDatasetIds`。
- provider 切换必须通过显式迁移/重绑定动作完成。

### 阶段 3：FastGPT 文档上传代理

目标：保留当前项目的“上传文档”体验。

改动：

- 后端接收文件。
- 调用 FastGPT Dataset localFile 上传 API。
- SQLite 记录逻辑文档、版本、FastGPT collection/file id。
- 替换文档采用“新版本成功后再移除旧版本”的策略。

验收：

- 上传文档后 FastGPT 可检索。
- 替换失败时旧版本仍可用。
- 删除文档只删除目标 FastGPT collection，不误删其他群资料。

## 数据和配置迁移

### 不迁移的内容

- 百炼 `indexJobId`。
- 百炼 `documentIds`。
- 百炼 Workspace 成员关系。
- 百炼文件解析任务状态。

这些都是百炼内部生命周期，不应迁到 FastGPT。

### 需要人工重建的内容

- FastGPT Dataset。
- FastGPT App。
- 文档上传。
- App 与 Dataset 绑定。
- API Key。

### 可以保留的内容

- 群绑定。
- BotProfile。
- Style。
- replyTriggers。
- routeExamples。
- fallbackPolicy。
- SQLite 对话历史和任务状态。

## 验收标准

### 后端

- `python -m pytest backend/tests -q -p no:cacheprovider` 通过。
- `python -m py_compile` 或现有 `scripts/self-test.ps1` 通过。
- 没有真实密钥进入 git diff。
- `provider=fastgpt` 缺少 App/Dataset 配置时给出明确错误。
- `SUPPORTED_PROVIDERS` 接受 `fastgpt`。
- `normalize_config()`、`public_config()`、`merge_public_config()` 都保留并保护 FastGPT 字段。
- `configuration/loader.py` 能把 YAML 中的 FastGPT 字段读入 `KnowledgeBase`。
- `provider=aliyun_bailian` 旧配置仍可作为回滚路径运行。

### 管理端

- `npm run build` 通过。
- FastGPT 配置项不展示 API Key。
- provider 切换不会丢失已有 bot/style/binding 配置。

### 运行

- `DRY_RUN=true`：真实微信群消息触发后只生成拟回复，不发送。
- `DRY_RUN=false`：只在 `LISTEN_GROUPS` 白名单内回复。
- FastGPT 服务不可用时，任务进入失败/重试，不自动胡编回答。
- 知识库未命中时按 `fallbackPolicy` 追问或走联网兜底。

## 测试计划

新增测试：

```text
backend/tests/test_fastgpt_knowledge.py
backend/tests/test_fastgpt_config_store.py
backend/tests/test_fastgpt_answer_chain.py
```

重点用例：

- FastGPT provider 配置校验。
- FastGPT API 失败时错误可读。
- FastGPT 检索结果标准化。
- 多群绑定不同 FastGPT Dataset。
- 未绑定群不调用 FastGPT。
- `DRY_RUN` 不发送微信。
- 百炼 provider 回归不被破坏。

## 环境变量清单

保留：

```ini
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
DRY_RUN=true
LISTEN_GROUPS=
BOT_MENTION_NAMES=
BOT_STATE_DB=runtime/bot_state.db
```

新增：

```ini
FASTGPT_BASE_URL=http://127.0.0.1:3000
FASTGPT_API_KEY=
FASTGPT_TIMEOUT_SECONDS=30
FASTGPT_DEFAULT_TOP_K=5
FASTGPT_DEFAULT_MIN_SCORE=0.2
```

FastGPT 的具体 provider 和模式不放 `.env`，放在单个 `knowledgeBases[]`：

```yaml
provider: fastgpt
fastgptMode: search_test
```

后续可删除：

```ini
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
ALIYUN_BAILIAN_ENDPOINT=
ALIYUN_BAILIAN_WORKSPACE_ID=
KNOWLEDGE_FILE_POLL_INTERVAL_SECONDS=
```

删除条件：FastGPT 上传、替换、删除、检索全部跑通，并且不再需要百炼回滚。

## 文件改造清单

优先改：

```text
backend/src/ai_ta_bot/config.py
backend/src/ai_ta_bot/configuration/models.py
backend/src/ai_ta_bot/configuration/loader.py
backend/src/ai_ta_bot/config_store.py
backend/src/ai_ta_bot/knowledge/answer_generator.py
backend/src/ai_ta_bot/knowledge/__init__.py
backend/src/ai_ta_bot/knowledge/provider_protocol.py
backend/src/ai_ta_bot/knowledge/fastgpt_knowledge.py
backend/tests/test_fastgpt_knowledge.py
backend/tests/test_fastgpt_config_store.py
backend/tests/test_fastgpt_answer_chain.py
config/bot.yaml
backend/.env.example
README.md
STARTUP.md
```

第二阶段改：

```text
backend/src/ai_ta_bot/admin/routers/knowledge.py
backend/src/ai_ta_bot/knowledge/cloud_knowledge_admin.py
backend/src/ai_ta_bot/persistence/knowledge_document_repository.py
admin-ui/src/App.jsx
admin-ui/src/styles.css
```

## 风险和处理

### FastGPT 服务比百炼更重

FastGPT 自部署通常需要多个容器。客户电脑配置差时，不适合和桌面微信一起跑。

处理：推荐私有服务器或 Windows 主机 + Docker Desktop；低配电脑只跑微信代理，FastGPT 放局域网服务器。

### DeepSeek 不是 embedding 模型

DeepSeek 继续用于回答生成，但知识库检索还需要 embedding 模型。

处理：FastGPT 里单独配置 embedding 模型。不要把“DeepSeek 作为大模型”理解为“所有向量检索也由 DeepSeek 完成”。

### FastGPT App 对话会吞掉本项目回答风格

如果直接调用 FastGPT App 生成答案，本项目的回答 prompt、群风格和引用控制会变弱。

处理：MVP 可先这样跑通，长期应切到 Dataset 检索模式，让本项目负责最终生成。

### 个人微信自动化仍有不稳定性

FastGPT 解决知识库，不解决微信客户端 UI 自动化的不确定性。

处理：继续保留 `DRY_RUN`、白名单、发送后验证、单实例锁和错误日志。

## 推荐提交拆分

1. `docs: add fastgpt local kb migration handoff`
2. `refactor: introduce knowledge provider interface`
3. `feat: add fastgpt knowledge client`
4. `feat: support fastgpt provider config` — 包含 `SUPPORTED_PROVIDERS`、`normalize_config()`、`validate_config()`、`public_config()`、`merge_public_config()` 全部 config_store 改动
5. `feat: wire fastgpt retrieval into answer chain`
6. `test: cover fastgpt provider routing`
7. `docs: update startup for fastgpt local knowledge`

## 官方资料

- FastGPT GitHub：<https://github.com/labring/FastGPT>
- FastGPT Docker Compose 自部署：<https://doc.fastgpt.io/en/self-host/deploy/docker>
- FastGPT OpenAPI 介绍：<https://doc.fastgpt.io/en/openapi/intro>
- FastGPT 知识库 API：<https://doc.fastgpt.io/en/openapi/dataset>
- FastGPT 对话接口：<https://doc.fastgpt.io/zh-CN/openapi/chat>
- FastGPT 环境变量说明：<https://doc.fastgpt.io/zh-CN/self-host/config/env>
- DeepSeek API 文档：<https://api-docs.deepseek.com/>
- DeepSeek 模型与价格：<https://api-docs.deepseek.com/quick_start/pricing>
