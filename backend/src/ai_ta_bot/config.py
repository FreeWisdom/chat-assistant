"""环境配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / "backend" / ".env")

# DeepSeek / LLM
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# 微信任务处理
CHAT_SEARCH_TIMEOUT = float(os.getenv("CHAT_SEARCH_TIMEOUT", "2"))
TASK_WORKER_INTERVAL = float(os.getenv("TASK_WORKER_INTERVAL", "0.5"))

# 开发/试跑模式
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"  # 会回复自己发的消息，用于自测
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"    # 只读消息、生成回答，不真发送到群（首次启动安全网）
TEST_GROUP = os.getenv("TEST_GROUP", "")                      # 指定后只监听这个群（忽略其他 binding），留空则监听全部
REQUIRE_TEST_GROUP = os.getenv("REQUIRE_TEST_GROUP", "true").lower() == "true"

# 知识库检索
KNOWLEDGE_CHUNK_SIZE = int(os.getenv("KNOWLEDGE_CHUNK_SIZE", "500"))
KNOWLEDGE_CHUNK_OVERLAP = int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP", "100"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

# 本地向量库；依赖不可用时会自动降级为关键词检索。
VECTOR_SEARCH_ENABLED = os.getenv("VECTOR_SEARCH_ENABLED", "false").lower() == "true"
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", "runtime/vector_store/chroma")
INDEX_MANIFEST_PATH = os.getenv("INDEX_MANIFEST_PATH", "runtime/vector_store/index_manifest.json")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "ai_ta_bot_knowledge")
CHROMA_BATCH_SIZE = int(os.getenv("CHROMA_BATCH_SIZE", "64"))
VECTOR_MAX_DISTANCE = float(os.getenv("VECTOR_MAX_DISTANCE", "0.65"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

# 运行状态
BOT_STATE_DB = os.getenv("BOT_STATE_DB", "runtime/bot_state.db")

# 网页知识库
WEB_FETCH_TIMEOUT = float(os.getenv("WEB_FETCH_TIMEOUT", "12"))
WEB_MAX_PAGES_PER_KB = int(os.getenv("WEB_MAX_PAGES_PER_KB", "50"))
WEB_USER_AGENT = os.getenv(
    "WEB_USER_AGENT",
    "ai-ta-bot/0.1 (+local knowledge connector)",
)

# 本地管理/平台同步服务
ADMIN_SYNC_TOKEN = os.getenv("ADMIN_SYNC_TOKEN", "")
ADMIN_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ADMIN_CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
