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

# 云知识库检索
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
KNOWLEDGE_RETRIEVAL_MIN_SCORE = float(
    os.getenv("KNOWLEDGE_RETRIEVAL_MIN_SCORE", "0.2")
)
KNOWLEDGE_RETRIEVAL_TIMEOUT_SECONDS = float(
    os.getenv("KNOWLEDGE_RETRIEVAL_TIMEOUT_SECONDS", "20")
)
KNOWLEDGE_RETRIEVAL_MAX_ATTEMPTS = int(
    os.getenv("KNOWLEDGE_RETRIEVAL_MAX_ATTEMPTS", "2")
)
KNOWLEDGE_UPLOAD_MAX_FILES = int(
    os.getenv("KNOWLEDGE_UPLOAD_MAX_FILES", "10")
)
KNOWLEDGE_UPLOAD_MAX_FILE_BYTES = int(
    os.getenv("KNOWLEDGE_UPLOAD_MAX_FILE_BYTES", str(100 * 1024 * 1024))
)
KNOWLEDGE_UPLOAD_HTTP_TIMEOUT_SECONDS = float(
    os.getenv("KNOWLEDGE_UPLOAD_HTTP_TIMEOUT_SECONDS", "120")
)
KNOWLEDGE_FILE_PARSE_TIMEOUT_SECONDS = float(
    os.getenv("KNOWLEDGE_FILE_PARSE_TIMEOUT_SECONDS", "600")
)
KNOWLEDGE_FILE_POLL_INTERVAL_SECONDS = float(
    os.getenv("KNOWLEDGE_FILE_POLL_INTERVAL_SECONDS", "5")
)
ALIYUN_BAILIAN_ACCESS_KEY_ID = os.getenv(
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "",
)
ALIYUN_BAILIAN_ACCESS_KEY_SECRET = os.getenv(
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "",
)
ALIYUN_BAILIAN_ENDPOINT = os.getenv(
    "ALIYUN_BAILIAN_ENDPOINT",
    "bailian.cn-beijing.aliyuncs.com",
)
ALIYUN_BAILIAN_WORKSPACE_ID = os.getenv(
    "ALIYUN_BAILIAN_WORKSPACE_ID",
    "",
).strip()

# 运行状态
BOT_STATE_DB = os.getenv("BOT_STATE_DB", "runtime/bot_state.db")
BOT_LOCK_FILE = os.getenv("BOT_LOCK_FILE", "runtime/bot.lock")
BOT_HEALTH_PATH = os.getenv("BOT_HEALTH_PATH", "runtime/bot_health.json")

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
