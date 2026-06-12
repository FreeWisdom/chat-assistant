"""
消息分析模块
判断消息是否为提问，提取问题内容
"""
import re
import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# 冷却管理
_last_reply: dict[str, float] = defaultdict(float)


def is_in_cooldown(key: str, cooldown_seconds: int) -> bool:
    return (time.time() - _last_reply[key]) < cooldown_seconds


def record_reply(key: str):
    _last_reply[key] = time.time()


# 提问检测正则模式
_QUESTION_PATTERNS = [
    r"吗[？?]?\s*$",              # 以"吗"结尾
    r"怎么.{2,}",                  # 包含"怎么"
    r"为什么.{2,}",                # 包含"为什么"
    r"如何.{2,}",                  # 包含"如何"
    r"能不能|可以不可以",           # 包含"能不能"
    r"什么.{0,2}(是|叫|意思)",     # 包含"什么是"
    r"\?{2,}|？{2,}",             # 多个问号
]

# 报错关键词
_ERROR_WORDS = ["Error", "错误", "报错", "异常", "Traceback", "Exception", "failed"]


def analyze_message(text: str, course, smart_detection: bool = True) -> dict:
    """
    分析消息是否为提问。
    返回: {"is_question": bool, "question_text": str}
    """
    text = text.strip()
    if not text:
        return {"is_question": False, "question_text": ""}

    # 1. 触发词匹配（配置文件中定义的关键词）
    for trigger in course.reply_triggers:
        if trigger in text:
            return {"is_question": True, "question_text": text}

    # 2. #举手 标记 — 包含 #举手 的消息一律回复
    if "#举手" in text:
        cleaned = text.replace("#举手", "").strip()
        return {"is_question": True, "question_text": cleaned or text}

    # 3. 智能检测
    if smart_detection:
        for p in _QUESTION_PATTERNS:
            if re.search(p, text):
                return {"is_question": True, "question_text": text}

        # 检测报错信息
        text_lower = text.lower()
        for w in _ERROR_WORDS:
            if w.lower() in text_lower:
                return {"is_question": True, "question_text": text}

    return {"is_question": False, "question_text": ""}
