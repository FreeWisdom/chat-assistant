"""环境配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / "backend" / ".env")


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    for separator in ("，", "；", ";", "\n"):
        raw = raw.replace(separator, ",")
    return tuple(dict.fromkeys(
        item.strip()
        for item in raw.split(",")
        if item.strip()
    ))


# DeepSeek / LLM
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# 微信任务处理
CHAT_SEARCH_TIMEOUT = float(os.getenv("CHAT_SEARCH_TIMEOUT", "2"))
TASK_WORKER_INTERVAL = float(os.getenv("TASK_WORKER_INTERVAL", "0.5"))
GROUP_WORKER_COUNT = int(os.getenv("GROUP_WORKER_COUNT", "4"))
TASK_MAX_ATTEMPTS = int(os.getenv("TASK_MAX_ATTEMPTS", "3"))
TASK_RETRY_BASE_SECONDS = float(os.getenv("TASK_RETRY_BASE_SECONDS", "5"))
TASK_RETRY_MAX_SECONDS = float(os.getenv("TASK_RETRY_MAX_SECONDS", "60"))
SEND_VERIFY_TIMEOUT = float(os.getenv("SEND_VERIFY_TIMEOUT", "5"))
SEND_VERIFY_INTERVAL = float(os.getenv("SEND_VERIFY_INTERVAL", "0.5"))

# 开发/试跑模式
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"  # 会回复自己发的消息，用于自测
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"    # 只读消息、生成回答，不真发送到群（首次启动安全网）
TEST_GROUP = os.getenv("TEST_GROUP", "").strip()              # 兼容旧版单群配置
LISTEN_GROUPS = _env_list("LISTEN_GROUPS") or ((TEST_GROUP,) if TEST_GROUP else ())
BOT_MENTION_NAMES = _env_list("BOT_MENTION_NAMES")
REQUIRE_LISTEN_GROUPS = os.getenv(
    "REQUIRE_LISTEN_GROUPS",
    os.getenv("REQUIRE_TEST_GROUP", "true"),
).lower() == "true"
REQUIRE_TEST_GROUP = REQUIRE_LISTEN_GROUPS                     # 兼容旧调用

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
BOT_LOCK_FILE = os.getenv("BOT_LOCK_FILE", "runtime/bot.lock")
BOT_HEALTH_PATH = os.getenv("BOT_HEALTH_PATH", "runtime/bot_health.json")

# 网页知识库
WEB_FETCH_TIMEOUT = float(os.getenv("WEB_FETCH_TIMEOUT", "12"))
WEB_MAX_PAGES_PER_KB = int(os.getenv("WEB_MAX_PAGES_PER_KB", "50"))
WEB_USER_AGENT = os.getenv(
    "WEB_USER_AGENT",
    "ai-ta-bot/0.1 (+local knowledge connector)",
)

# 实时联网搜索：由 LLM 路由器判定为时效/外部事实，或知识库未命中时调用。
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "false").lower() == "true"
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "tavily").strip().lower()
WEB_SEARCH_TIMEOUT = float(os.getenv("WEB_SEARCH_TIMEOUT", "12"))
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

# Tavily（英文搜索为主，WEB_SEARCH_PROVIDER=tavily 时使用）
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_SEARCH_URL = os.getenv("TAVILY_SEARCH_URL", "https://api.tavily.com/search")
WEB_SEARCH_DEPTH = os.getenv("WEB_SEARCH_DEPTH", "advanced")
WEB_SEARCH_COUNTRY = os.getenv("WEB_SEARCH_COUNTRY", "china")
WEB_SEARCH_TIME_RANGE = os.getenv("WEB_SEARCH_TIME_RANGE", "month").strip()
WEB_SEARCH_FRESH_TIME_RANGE = os.getenv("WEB_SEARCH_FRESH_TIME_RANGE", "week").strip()
WEB_SEARCH_FALLBACK_TIME_RANGE = os.getenv(
    "WEB_SEARCH_FALLBACK_TIME_RANGE",
    "year",
).strip()

# 火山引擎联网搜索（中文搜索推荐，WEB_SEARCH_PROVIDER=volcengine 时使用）
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY", "")
VOLCENGINE_SEARCH_URL = os.getenv(
    "VOLCENGINE_SEARCH_URL",
    "https://api.volcengine.com/web_search/v1/query",
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
