"""
微信机器人模块 — 基于 wxauto4（免费版）
通过轮询检测新消息并自动回复
"""
import hashlib
import random
import time
import logging
from wxauto4 import WeChat
from wxauto4.param import WxParam
from course_manager import CourseManager, RuntimeBotConfig
from message_analyzer import analyze_message, is_in_cooldown, record_reply
from rag_engine import RAGEngine
import config

logger = logging.getLogger(__name__)


def _parse_msg(msg) -> tuple[str, str, str]:
    """解析消息对象，返回 (content, sender, msg_type)"""
    if hasattr(msg, 'content'):
        content = str(msg.content).strip()
    elif isinstance(msg, dict):
        content = str(msg.get('content', '')).strip()
    elif isinstance(msg, str):
        content = msg.strip()
    else:
        content = str(msg).strip()

    sender = ''
    if hasattr(msg, 'sender'):
        sender = str(msg.sender)
    elif hasattr(msg, 'attr'):
        sender = str(msg.attr)

    msg_type = ''
    if hasattr(msg, 'type'):
        msg_type = str(msg.type)

    return content, sender, msg_type


def _msg_fingerprint(msg) -> str:
    """生成消息指纹，用于去重"""
    content, sender, msg_type = _parse_msg(msg)
    raw = f"{sender}|{msg_type}|{content}"
    return hashlib.md5(raw.encode('utf-8', errors='ignore')).hexdigest()


# 不需要回复的消息类型前缀
_SKIP_PREFIXES = ('[动画表情]', '[图片]', '[视频通话]', '[语音]', '[文件]', '[小程序]', '[链接]')


class WeChatBot:
    """AI 助教微信机器人"""

    def __init__(self, course_manager: CourseManager, rag_engine: RAGEngine):
        self.cm = course_manager
        self.rag = rag_engine
        WxParam.SEARCH_CHAT_TIMEOUT = config.CHAT_SEARCH_TIMEOUT
        self.wx = WeChat()
        self.chat_history: dict[str, list[dict]] = {}
        self._processed: set[str] = set()
        self._current_group: str | None = None
        self._running = False

    def start(self):
        """启动机器人"""
        logger.info("=" * 50)
        logger.info("   AI 助教机器人 启动中 (wxauto4)")
        logger.info("=" * 50)

        # 验证群并标记已有消息
        self._init_groups()

        logger.info(f"监听群: {list(self.cm.group_map.keys())}")
        logger.info(f"轮询间隔: {config.POLL_INTERVAL}s, 冷却: {config.COOLDOWN_SECONDS}s")
        if config.DEV_MODE:
            logger.info("🔧 开发模式: 会回复自己的消息")
        if config.DRY_RUN:
            logger.info("🛡️  DRY_RUN 模式: 只生成回答不发送，使用 '*** DRY_RUN ***' 日志标记")
        logger.info("开始监听，按 Ctrl+C 停止")
        self._running = True

        try:
            self._poll()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"运行异常: {e}", exc_info=True)

    def _init_groups(self):
        """验证群是否存在，标记所有已有消息为已处理"""
        logger.info("正在初始化课程群...")
        for group_name in self.cm.group_map:
            runtime = self.cm.get_course(group_name)
            try:
                self._switch_group(group_name, force=True)
                messages = self.wx.GetAllMessage()
                count = len(messages) if messages else 0
                if messages:
                    for msg in messages:
                        self._processed.add(_msg_fingerprint(msg))
                logger.info(f"  ✅ {group_name} → {runtime.name} (已有 {count} 条消息)")
            except Exception as e:
                logger.warning(f"  ⚠️ {group_name} 初始化失败: {e}")
                logger.warning(f"     请手动点开该群清掉未读消息后重试")

    def _poll(self):
        """轮询检测新消息"""
        logger.info("轮询已启动...")
        group_list = list(self.cm.group_map.keys())
        poll_id = 0

        while self._running:
            poll_id += 1
            for group_name in group_list:
                if not self._running:
                    break

                runtime = self.cm.get_course(group_name)
                if not runtime or self.cm.is_excluded(group_name):
                    continue

                try:
                    # 切换到目标群；单群且未被强制切换时会复用当前会话，避免反复搜索。
                    self._switch_group(group_name, force=config.FORCE_SWITCH_EACH_POLL)

                    # 读取消息
                    messages = self.wx.GetAllMessage()
                    msg_count = len(messages) if messages else 0
                    logger.info(f"[#{poll_id}] [{group_name}] 读取到 {msg_count} 条消息, 已处理指纹: {len(self._processed)}")

                    if not messages:
                        continue

                    # 找新消息
                    new_count = 0
                    for msg in messages:
                        fp = _msg_fingerprint(msg)
                        if fp in self._processed:
                            continue
                        new_count += 1
                        content, sender, msg_type = _parse_msg(msg)
                        logger.info(f"[#{poll_id}] 新消息: sender={sender}, type={msg_type}, content={content[:50]}")

                        # 处理消息，成功才标记指纹
                        if self._handle_message(msg, group_name, runtime):
                            self._processed.add(fp)

                    if new_count > 0:
                        logger.info(f"[#{poll_id}] [{group_name}] 本轮处理了 {new_count} 条新消息")

                except Exception as e:
                    logger.error(f"[#{poll_id}] [{group_name}] 轮询异常: {e}")

            time.sleep(config.POLL_INTERVAL)

    def _switch_group(self, group_name: str, force: bool = False):
        """切换到指定群；已在目标群时默认不重复搜索。"""
        if not force and self._current_group == group_name:
            return

        result = self.wx.ChatWith(group_name, exact=True)
        if not result:
            self._current_group = None
            raise RuntimeError(f"未找到微信群: {group_name}")

        self._current_group = group_name
        time.sleep(config.POLL_LOAD_WAIT)

    def _handle_message(self, msg, group_topic: str, runtime: RuntimeBotConfig) -> bool:
        """处理单条消息。返回 True=已处理可标记指纹，False=跳过下次重试"""
        try:
            content, sender, msg_type = _parse_msg(msg)
            logger.info(f"    处理消息: sender={sender}, type={msg_type}, content={content[:40]}")

            if not content:
                logger.info(f"    → 跳过: 空消息")
                return True

            # 过滤系统消息
            if msg_type in ('sys', 'app', 'time'):
                logger.info(f"    → 跳过: 系统消息 type={msg_type}")
                return True

            # 过滤自己的消息（开发模式除外）
            if not config.DEV_MODE:
                if msg_type == 'self' or sender in (self.wx.nickname, 'self'):
                    logger.info(f"    → 跳过: 自己的消息")
                    return True
            else:
                logger.info(f"    → 开发模式，不过滤自己的消息")

            # 过滤非文本
            if any(content.startswith(p) for p in _SKIP_PREFIXES):
                logger.info(f"    → 跳过: 非文本内容")
                return True

            # 是否为提问（含 @ 触发和关键词触发）
            result = analyze_message(content, runtime, self.cm.smart_detection,
                                     bot_name=runtime.bot.name)
            if not result["is_question"]:
                logger.info(f"    → 跳过: 非提问")
                return True

            # 冷却
            cooldown_key = f"{group_topic}:{sender}"
            if is_in_cooldown(cooldown_key, self.cm.cooldown_seconds):
                logger.info(f"    → 冷却中: {sender}")
                return False

            logger.info(f"    ✅ 检测到提问! {sender}: {content[:60]}")

            # RAG 生成回答
            self._add_history(group_topic, "user", f"{sender}: {content}")
            history = self.chat_history.get(group_topic, [])
            answer = self.rag.answer(
                result["question_text"],
                runtime,
                history,
                sender=sender,
                group_name=group_topic,
            )
            logger.info(f"    📝 RAG 生成回答: {answer[:60]}...")

            # 发送
            self._send_reply(answer, group_topic, sender)

            record_reply(cooldown_key)
            self._add_history(group_topic, "assistant", answer)
            return True

        except Exception as e:
            logger.error(f"处理消息异常: {e}", exc_info=True)
            try:
                _, sender, __ = _parse_msg(msg)
                self._send_reply("抱歉，消息处理异常，稍后再试？", group_topic, sender)
            except Exception:
                pass
            return True

    def _send_reply(self, text: str, group_name: str, sender: str = ""):
        """发送回复，超长则分段。sender 非空时添加 @ 提及。"""
        prefix = f"@{sender} " if sender else ""

        if config.DRY_RUN:
            preview = text[:60].replace("\n", " ")
            logger.info(f"  🛡️  *** DRY_RUN *** [{group_name}] @{sender or '无提及'}: {preview}...")
            return

        full_text = f"{prefix}{text}"
        max_len = config.MAX_REPLY_LENGTH

        if len(full_text) <= max_len:
            self._sleep_before_reply(full_text)
            if self._current_group == group_name:
                self.wx.SendMsg(full_text)
            else:
                self.wx.SendMsg(full_text, group_name, exact=True)
            logger.info(f"  ✅ 已回复 [{group_name}]: {text[:50]}...")
            return

        # 按段落分段（首段带 @ 提及）
        parts = []
        paragraphs = text.split('\n\n')
        current = ''
        effective_max = max_len - len(prefix)
        for para in paragraphs:
            if len(current) + len(para) + 2 > effective_max and current:
                parts.append(current.strip())
                current = para
            else:
                current = current + '\n\n' + para if current else para
        if current.strip():
            parts.append(current.strip())

        for i, part in enumerate(parts):
            segment = f"{prefix}{part}" if i == 0 else part
            self._sleep_before_reply(segment)
            if self._current_group == group_name:
                self.wx.SendMsg(segment)
            else:
                self.wx.SendMsg(segment, group_name, exact=True)
            logger.info(f"  ✅ 已回复 [{group_name}] ({i+1}/{len(parts)}): {part[:40]}...")
            if i < len(parts) - 1:
                time.sleep(1)

    def _sleep_before_reply(self, text: str):
        min_delay = max(0.0, config.REPLY_DELAY_MIN)
        max_delay = max(min_delay, config.REPLY_DELAY_MAX)
        delay = random.uniform(min_delay, max_delay)
        delay += min(len(text) / 120, 2.0)
        logger.info(f"  等待 {delay:.1f}s 后发送，模拟正常阅读和输入节奏")
        time.sleep(delay)

    def _add_history(self, group_topic: str, role: str, content: str):
        if group_topic not in self.chat_history:
            self.chat_history[group_topic] = []
        self.chat_history[group_topic].append({"role": role, "content": content})
        if len(self.chat_history[group_topic]) > 20:
            self.chat_history[group_topic] = self.chat_history[group_topic][-20:]
