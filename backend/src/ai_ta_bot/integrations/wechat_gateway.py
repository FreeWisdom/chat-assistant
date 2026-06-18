"""wxauto4 adapter for listening, task persistence, and replies."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from wxauto4 import HandRaiseReplyWorkflow, WeChat, WxParam
from wxauto4.reply_queue import STATUS_PENDING, ReplyTask

from ..domain import HandRaiseTriggerPolicy

logger = logging.getLogger(__name__)


class WeChatGateway:
    """Keep all wxauto4-specific behavior outside application services."""

    def __init__(
        self,
        *,
        allowed_chats: Sequence[str],
        db_path: str | Path,
        trigger_policy: HandRaiseTriggerPolicy,
        dry_run: bool,
        allow_self: bool = False,
        search_timeout: float = 2.0,
    ):
        self.allowed_chats = tuple(dict.fromkeys(allowed_chats))
        if not self.allowed_chats:
            raise ValueError("至少需要配置一个允许监听的微信群")

        self.trigger_policy = trigger_policy
        self.dry_run = dry_run
        self.allow_self = allow_self
        WxParam.SEARCH_CHAT_TIMEOUT = search_timeout
        WxParam.MESSAGE_HASH = True

        self.wx = WeChat()
        self.workflow = HandRaiseReplyWorkflow(
            self.wx,
            db_path=db_path,
            allowed_chats=self.allowed_chats,
        )

    def _listener_callback(self, message, chat):
        content = str(getattr(message, "content", "") or "").strip()
        if not self.trigger_policy.matches(content):
            return None

        attr = str(getattr(message, "attr", "") or "")
        if attr != "friend" and not (self.allow_self and attr == "self"):
            return None

        try:
            info = chat.ChatInfo() or {}
        except Exception:
            info = {}
        chat_name = (
            info.get("chat_name")
            or getattr(chat, "who", None)
            or getattr(chat, "nickname", None)
        )
        if not chat_name or chat_name not in self.allowed_chats:
            logger.warning("忽略非白名单聊天消息: %s", chat_name or "<unknown>")
            return None
        if info.get("chat_type") not in (None, "", "group"):
            return None

        task = self.workflow.store.enqueue(
            chat_name=chat_name,
            sender=str(getattr(message, "sender", "") or "unknown"),
            content=content,
            marker="#举手",
            message_id=str(getattr(message, "id", "") or "") or None,
            message_hash=str(getattr(message, "hash", "") or "") or None,
            message_type=str(getattr(message, "type", "") or "") or None,
        )
        logger.info(
            "提问任务已入库: task=%s chat=%s sender=%s",
            task.id,
            task.chat_name,
            task.sender,
        )
        return task

    def start(self) -> None:
        for chat_name in self.allowed_chats:
            response = self.wx.AddListenChat(chat_name, self._listener_callback)
            if not response:
                raise RuntimeError(
                    f"监听微信群失败: {chat_name}: "
                    f"{response.get('message') if response else 'unknown error'}"
                )
            logger.info("已注册微信监听: %s", chat_name)

    def stop(self) -> None:
        try:
            self.wx.StopListening()
        except Exception:
            logger.exception("停止微信监听失败")

    def pending_tasks(self, limit: int = 20) -> list[ReplyTask]:
        return self.workflow.store.list((STATUS_PENDING,), limit=limit)

    def reply(self, task_id: int, answer: str):
        if not self.dry_run:
            return self.workflow.reply(task_id, answer)

        task = self.workflow.store.claim(task_id)
        if task is None:
            raise RuntimeError(f"任务不存在或已被处理: {task_id}")
        logger.info(
            "*** DRY_RUN *** task=%s chat=%s answer=%s",
            task.id,
            task.chat_name,
            answer[:120].replace("\n", " "),
        )
        self.workflow.store.mark_replied(task.id, answer)
        return {"status": "success", "message": "dry-run"}

    def mark_failed(self, task_id: int, error: str) -> None:
        task = self.workflow.store.claim(task_id)
        if task is None:
            return
        self.workflow.store.mark_failed(task.id, error)
