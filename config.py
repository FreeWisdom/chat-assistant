"""环境配置"""
import os
from dotenv import load_dotenv

load_dotenv()

# DeepSeek / LLM
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# Tavily 联网搜索
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# 机器人行为
BOT_NAME = os.getenv("BOT_NAME", "AI助教")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "30"))
MAX_REPLY_LENGTH = int(os.getenv("MAX_REPLY_LENGTH", "500"))

# 轮询配置
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3"))       # 轮询间隔（秒）
POLL_LOAD_WAIT = float(os.getenv("POLL_LOAD_WAIT", "1.5"))  # 切换聊天后等待时间（秒）

# 开发模式
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"  # 开发模式：回复自己的消息
