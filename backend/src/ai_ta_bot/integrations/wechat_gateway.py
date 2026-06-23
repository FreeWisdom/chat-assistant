"""wxauto4 adapter for listening, task persistence, and replies."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time
from types import MethodType
from typing import Sequence
import unicodedata

from wxauto4 import HandRaiseReplyWorkflow, WeChat, WxParam, WxResponse
from wxauto4.reply_queue import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    ReplyTask,
)

from ..domain import HandRaiseTriggerPolicy
from ..persistence import ReliableReplyTaskStore, TaskMetadataRepository

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
        bot_names: Sequence[str] = (),
        search_timeout: float = 2.0,
        task_metadata: TaskMetadataRepository | None = None,
        max_attempts: int = 3,
        retry_base_seconds: float = 5,
        retry_max_seconds: float = 60,
        send_verify_timeout: float = 5,
        send_verify_interval: float = 0.5,
        wx=None,
        workflow=None,
    ):
        self.allowed_chats = tuple(dict.fromkeys(allowed_chats))
        if not self.allowed_chats:
            raise ValueError("至少需要配置一个允许监听的微信群")

        self.trigger_policy = trigger_policy
        self.dry_run = dry_run
        self.allow_self = allow_self
        self.bot_names = tuple(dict.fromkeys(bot_names))
        self.db_path = db_path
        self.task_metadata = task_metadata or TaskMetadataRepository(db_path)
        self.max_attempts = max(1, max_attempts)
        self.retry_base_seconds = max(0.1, retry_base_seconds)
        self.retry_max_seconds = max(
            self.retry_base_seconds,
            retry_max_seconds,
        )
        self.send_verify_timeout = max(0.1, send_verify_timeout)
        self.send_verify_interval = max(0.05, send_verify_interval)
        WxParam.SEARCH_CHAT_TIMEOUT = search_timeout
        WxParam.MESSAGE_HASH = True

        self.wx = wx
        self.workflow = workflow
        self.registered_chats: dict[str, str] = {}
        self._listen_windows: dict[str, object] = {}
        self._listener_stats_lock = threading.Lock()
        self._listener_recovery_lock = threading.Lock()
        self._listener_recovery_path = (
            Path(self.db_path).resolve().parent / "listener_recovery.jsonl"
        )
        self._listener_stats = {
            "messages_seen": 0,
            "trigger_matches": 0,
            "tasks_persisted": 0,
            "callback_errors": 0,
            "recovered_tasks": 0,
        }
        self._last_listener_message_at = None
        self._last_persisted_task_at = None

    @staticmethod
    def _normalize_chat_name(value: str) -> str:
        text = unicodedata.normalize("NFC", str(value or "")).strip()
        return text.replace("\ufe0f", "").replace("\ufe0e", "")

    def _ensure_client(self) -> None:
        if self.wx is None:
            self.wx = WeChat()
        if self.workflow is None:
            self.workflow = HandRaiseReplyWorkflow(
                self.wx,
                db_path=self.db_path,
                allowed_chats=self.allowed_chats,
            )
            self.workflow.store = ReliableReplyTaskStore(self.db_path)

    def _metadata_repository(self) -> TaskMetadataRepository:
        repository = getattr(self, "task_metadata", None)
        if repository is None:
            repository = self.task_metadata = TaskMetadataRepository(
                self.db_path
            )
        return repository

    def _increment_listener_stat(self, name: str) -> None:
        if not hasattr(self, "_listener_stats_lock"):
            self._listener_stats_lock = threading.Lock()
            self._listener_stats = {}
        with self._listener_stats_lock:
            self._listener_stats[name] = self._listener_stats.get(name, 0) + 1

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _dispatch_listener_message(self, callback, message, chat, chat_name) -> None:
        """Persist a detected trigger synchronously before polling advances."""
        self._increment_listener_stat("messages_seen")
        self._last_listener_message_at = self._utcnow()
        try:
            callback(message, chat)
        except Exception:
            self._increment_listener_stat("callback_errors")
            logger.exception(
                "监听消息同步回调失败: chat=%s sender=%s content=%s",
                chat_name,
                getattr(message, "sender", ""),
                str(getattr(message, "content", "") or "")[:120],
            )

    def _write_recovery_event(
        self,
        enqueue_args: dict,
        context: dict | None = None,
    ) -> None:
        path = getattr(
            self,
            "_listener_recovery_path",
            Path(self.db_path).resolve().parent / "listener_recovery.jsonl",
        )
        lock = getattr(self, "_listener_recovery_lock", None)
        if lock is None:
            lock = self._listener_recovery_lock = threading.Lock()
        event = {
            **enqueue_args,
            "_context": context or {},
            "journaled_at": self._utcnow(),
        }
        with lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
                file.flush()
        logger.error(
            "触发任务已写入恢复队列: chat=%s content=%s",
            enqueue_args.get("chat_name"),
            str(enqueue_args.get("content", ""))[:120],
        )

    def _recover_listener_events(self) -> int:
        path = getattr(self, "_listener_recovery_path", None)
        if path is None or not path.exists():
            return 0
        lock = getattr(self, "_listener_recovery_lock", None)
        if lock is None:
            lock = self._listener_recovery_lock = threading.Lock()

        with lock:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                logger.exception("读取监听恢复队列失败: %s", path)
                return 0

            remaining = []
            recovered = 0
            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event.pop("journaled_at", None)
                    context = event.pop("_context", {})
                    task = self.workflow.store.enqueue(**event)
                    self._metadata_repository().save_context(
                        task.id,
                        trigger_type=str(
                            context.get("trigger_type") or event["marker"]
                        ),
                        quote_nickname=str(
                            context.get("quote_nickname") or ""
                        ),
                        quote_content=str(
                            context.get("quote_content") or ""
                        ),
                    )
                    recovered += 1
                except Exception:
                    remaining.append(line)
                    logger.exception("监听恢复任务重放失败")

            if remaining:
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_text(
                    "\n".join(remaining) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(path)
            else:
                path.unlink(missing_ok=True)

        if recovered:
            for _ in range(recovered):
                self._increment_listener_stat("recovered_tasks")
            logger.warning("已从监听恢复队列补回任务: count=%s", recovered)
        return recovered

    def _install_reliable_listener_dispatch(self) -> None:
        """Replace wxauto4's lossy async callback handoff with sync persistence.

        wxauto4 marks messages as consumed in ``GetNewMessage`` and then submits
        callbacks to a separate executor. If that handoff is skipped or stalls,
        the next poll cannot recover the message. The callback in this project
        only validates and writes SQLite, so it is safe and preferable to finish
        it synchronously in the polling thread. LLM/search/reply work remains in
        BotRunner's separate worker pool.
        """
        if self.wx is None or getattr(
            self.wx,
            "_ai_ta_reliable_dispatch_installed",
            False,
        ):
            return
        if not hasattr(self.wx, "_get_listen_messages"):
            return

        gateway = self

        def reliable_get_listen_messages(wx_self):
            try:
                import sys

                sys.stdout.flush()
            except Exception:
                pass

            gateway._recover_listener_events()
            for who, pair in list(getattr(wx_self, "listen", {}).items()):
                chat, callback = pair
                try:
                    if chat is None or not chat._api.exists():
                        wx_self.RemoveListenChat(who)
                        continue
                except Exception:
                    logger.exception("检查监听窗口失败: chat=%s", who)
                    continue

                try:
                    with wx_self._lock:
                        messages = list(chat.GetNewMessage())
                except Exception:
                    logger.exception("读取监听窗口消息失败: chat=%s", who)
                    continue

                for message in messages:
                    gateway._dispatch_listener_message(
                        callback,
                        message,
                        chat,
                        who,
                    )

        self.wx._get_listen_messages = MethodType(
            reliable_get_listen_messages,
            self.wx,
        )
        self.wx._ai_ta_reliable_dispatch_installed = True
        logger.info("已启用可靠监听分发：消息触发判断与任务入库同步完成")

    def _listener_callback(self, message, chat, expected_chat: str | None = None):
        original_content = str(
            getattr(message, "content", "") or ""
        ).strip()
        attr = str(getattr(message, "attr", "") or "")
        if attr != "friend" and not (self.allow_self and attr == "self"):
            return None

        trigger = self.trigger_policy.match_message(
            message,
            self._effective_bot_names(),
        )
        if trigger is None:
            return None
        self._increment_listener_stat("trigger_matches")

        info = {}
        if expected_chat:
            # start() 已验证独立监听窗口与配置群名一致。消息回调不能再次
            # 依赖 ChatInfo().chat_type：微信 UI 偶发取不到群人数控件时，
            # wxauto4 会把群聊默认识别为 friend，导致消息被静默丢弃。
            canonical_name = expected_chat
            chat_name = (
                getattr(chat, "who", None)
                or getattr(chat, "nickname", None)
                or canonical_name
            )
        else:
            try:
                info = chat.ChatInfo() or {}
            except Exception:
                info = {}
            chat_name = (
                info.get("chat_name")
                or getattr(chat, "who", None)
                or getattr(chat, "nickname", None)
            )
            canonical_name = chat_name
        if (
            not chat_name
            or not canonical_name
            or canonical_name not in self.allowed_chats
            or self._normalize_chat_name(chat_name)
            != self._normalize_chat_name(canonical_name)
        ):
            logger.warning("忽略非白名单聊天消息: %s", chat_name or "<unknown>")
            return None
        if not expected_chat and info.get("chat_type") not in (None, "", "group"):
            return None

        enqueue_args = {
            "chat_name": canonical_name,
            "sender": str(getattr(message, "sender", "") or "unknown"),
            # 保留微信原文，供 SearchMessageLocator 精确定位并引用回复。
            "content": original_content,
            "marker": trigger.marker,
            "message_id": str(getattr(message, "id", "") or "") or None,
            "message_hash": str(getattr(message, "hash", "") or "") or None,
            "message_type": str(getattr(message, "type", "") or "") or None,
        }
        trigger_context = {
            "trigger_type": trigger.trigger_type,
            "quote_nickname": str(
                getattr(message, "quote_nickname", "") or ""
            ),
            "quote_content": str(
                getattr(message, "quote_content", "") or ""
            ),
        }
        last_error = None
        for attempt in range(1, 4):
            try:
                task = self.workflow.store.enqueue(**enqueue_args)
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "触发任务入库失败，第%s/3次重试: chat=%s error=%s",
                    attempt,
                    canonical_name,
                    exc,
                )
                if attempt < 3:
                    time.sleep(0.05 * attempt)
        else:
            self._write_recovery_event(enqueue_args, trigger_context)
            raise RuntimeError(
                f"触发任务连续3次入库失败，已进入恢复队列: {last_error}"
            ) from last_error

        self._metadata_repository().save_context(
            task.id,
            **trigger_context,
        )
        self._increment_listener_stat("tasks_persisted")
        self._last_persisted_task_at = self._utcnow()
        logger.info(
            "提问任务已同步入库: task=%s chat=%s sender=%s trigger=%s",
            task.id,
            task.chat_name,
            task.sender,
            trigger.trigger_type,
        )
        return task

    def _effective_bot_names(self) -> tuple[str, ...]:
        names = list(getattr(self, "bot_names", ()))
        nickname = str(getattr(self.wx, "nickname", "") or "").strip()
        # 当前 wxauto4 在部分微信版本只返回窗口名“微信”，不能把它当群昵称。
        if nickname and nickname not in {"微信", "WeChat", "Weixin"}:
            names.append(nickname)
        return tuple(dict.fromkeys(names))

    def start(self) -> None:
        self._ensure_client()
        self._recover_listener_events()
        self._install_reliable_listener_dispatch()
        try:
            for chat_name in self.allowed_chats:
                callback = (
                    lambda message, chat, expected=chat_name:
                    self._listener_callback(message, chat, expected)
                )
                response = self.wx.AddListenChat(chat_name, callback)
                if not response:
                    message = (
                        response.get("message")
                        if hasattr(response, "get")
                        else "unknown error"
                    )
                    raise RuntimeError(f"监听微信群失败: {chat_name}: {message}")

                actual_name = (
                    getattr(response, "who", None)
                    or getattr(response, "nickname", None)
                    or chat_name
                )
                try:
                    info = response.ChatInfo() or {}
                    actual_name = info.get("chat_name") or actual_name
                except Exception:
                    pass
                if (
                    self._normalize_chat_name(actual_name)
                    != self._normalize_chat_name(chat_name)
                ):
                    raise RuntimeError(
                        f"监听窗口群名不匹配: requested={chat_name}, actual={actual_name}"
                    )
                self.registered_chats[chat_name] = str(actual_name)
                self._listen_windows[chat_name] = response
                logger.info(
                    "已注册微信监听: configured=%s actual=%s",
                    chat_name,
                    actual_name,
                )
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self.wx is None:
            return
        try:
            self.wx.StopListening()
        except Exception:
            logger.exception("停止微信监听失败")
        finally:
            self.registered_chats.clear()
            self._listen_windows.clear()

    def pending_tasks(self, limit: int = 20) -> list[ReplyTask]:
        self._ensure_client()
        candidates = self.workflow.store.list(
            (STATUS_PENDING, STATUS_FAILED),
            limit=max(limit * 10, 200),
        )
        pending = []
        for task in candidates:
            if task.chat_name not in self.allowed_chats:
                continue
            if task.status == STATUS_FAILED:
                if task.attempts >= self.max_attempts:
                    self._metadata_repository().set_phase(
                        task.id,
                        "dead_letter",
                        last_error=task.last_error,
                    )
                    continue
                if not self._metadata_repository().retry_due(task.id):
                    continue
            pending.append(task)
            if len(pending) >= limit:
                break
        return pending

    def reply(self, task_id: int, answer: str):
        self._ensure_client()
        locator = getattr(self.workflow, "locator", None)
        if (
            not self.dry_run
            and (locator is None or not hasattr(locator, "reply"))
        ):
            response = self.workflow.reply(task_id, answer)
            if response:
                self._metadata_repository().set_phase(
                    task_id,
                    "replied",
                    generated_answer=answer,
                    send_mode="workflow_compat",
                    verified=True,
                )
            return response

        task = self.workflow.store.claim(task_id)
        if task is None:
            return WxResponse.failure(f"任务不存在或已被处理: {task_id}")
        metadata = self._metadata_repository()
        metadata.set_phase(
            task.id,
            "sending",
            generated_answer=answer,
        )

        if self.dry_run:
            logger.info(
                "*** DRY_RUN *** task=%s chat=%s answer=%s",
                task.id,
                task.chat_name,
                answer[:120].replace("\n", " "),
            )
            self.workflow.store.mark_replied(task.id, answer)
            metadata.set_phase(
                task.id,
                "replied",
                send_mode="dry_run",
                verified=True,
            )
            return WxResponse.success("dry-run")

        if task.chat_name not in self.allowed_chats:
            return self._fail_claimed_task(
                task,
                f"聊天不在允许列表中: {task.chat_name}",
            )

        metadata.set_phase(task.id, "sending", send_mode="quote")
        try:
            quote_response = locator.reply(task, answer)
        except Exception as exc:
            quote_response = WxResponse.failure(str(exc))

        if quote_response and self._verify_sent_message(
            task.chat_name,
            answer,
        ):
            self.workflow.store.mark_replied(task.id, answer)
            metadata.set_phase(
                task.id,
                "replied",
                send_mode="quote",
                verified=True,
            )
            return WxResponse.success(
                "引用回复成功且已确认消息可见",
                data={"task_id": task.id, "send_mode": "quote"},
            )

        quote_error = (
            quote_response.get("message")
            if hasattr(quote_response, "get")
            else "引用回复未确认"
        )
        logger.warning(
            "引用回复失败或未确认，降级普通群消息: task=%s error=%s",
            task.id,
            quote_error,
        )
        metadata.set_phase(task.id, "sending", send_mode="fallback")
        fallback_response = self._send_plain_message(task.chat_name, answer)
        if fallback_response and self._verify_sent_message(
            task.chat_name,
            answer,
        ):
            self.workflow.store.mark_replied(task.id, answer)
            metadata.set_phase(
                task.id,
                "replied",
                send_mode="fallback",
                verified=True,
            )
            return WxResponse.success(
                "引用失败后已降级普通回复，并确认消息可见",
                data={"task_id": task.id, "send_mode": "fallback"},
            )

        fallback_error = (
            fallback_response.get("message")
            if hasattr(fallback_response, "get")
            else "普通回复未确认"
        )
        return self._fail_claimed_task(
            task,
            f"引用回复失败: {quote_error}; 普通回复失败或未确认: "
            f"{fallback_error}",
        )

    @staticmethod
    def _normalize_message_text(value: str) -> str:
        return " ".join(str(value or "").split())

    def _verify_sent_message(self, chat_name: str, answer: str) -> bool:
        chat = self._listen_windows.get(chat_name)
        if chat is None:
            logger.error("发送确认失败，监听子窗口不存在: %s", chat_name)
            return False

        expected = self._normalize_message_text(answer)
        deadline = time.monotonic() + self.send_verify_timeout
        while time.monotonic() < deadline:
            try:
                messages = chat.GetAllMessage()
            except Exception:
                logger.exception("读取群窗口验证发送结果失败: %s", chat_name)
                messages = []
            for message in reversed(list(messages or [])[-20:]):
                actual = self._normalize_message_text(
                    getattr(message, "content", "")
                )
                if actual == expected:
                    return True
            time.sleep(self.send_verify_interval)
        logger.error(
            "发送接口返回后未在群窗口读回消息: chat=%s answer=%s",
            chat_name,
            answer[:120].replace("\n", " "),
        )
        return False

    def _send_plain_message(self, chat_name: str, answer: str):
        chat = self._listen_windows.get(chat_name)
        if chat is None:
            return WxResponse.failure(f"监听子窗口不存在: {chat_name}")
        try:
            return chat.SendMsg(answer)
        except Exception as exc:
            logger.exception("普通群消息发送异常: chat=%s", chat_name)
            return WxResponse.failure(str(exc))

    def _fail_claimed_task(self, task, error: str):
        self.workflow.store.mark_failed(task.id, error)
        updated = self.workflow.store.get(task.id)
        attempts = updated.attempts if updated is not None else task.attempts
        phase = self._metadata_repository().schedule_retry(
            task.id,
            attempts=attempts,
            error=error,
            max_attempts=self.max_attempts,
            base_seconds=self.retry_base_seconds,
            max_seconds=self.retry_max_seconds,
        )
        return WxResponse.failure(
            error,
            data={
                "task_id": task.id,
                "phase": phase,
                "attempts": attempts,
            },
        )

    def mark_phase(
        self,
        task_id: int,
        phase: str,
        *,
        answer: str | None = None,
    ) -> None:
        self._metadata_repository().set_phase(
            task_id,
            phase,
            generated_answer=answer,
        )

    def mark_failed(self, task_id: int, error: str) -> None:
        self._ensure_client()
        task = self.workflow.store.get(task_id)
        if task is None:
            return
        if task.status == STATUS_FAILED:
            self._metadata_repository().schedule_retry(
                task.id,
                attempts=task.attempts,
                error=error,
                max_attempts=self.max_attempts,
                base_seconds=self.retry_base_seconds,
                max_seconds=self.retry_max_seconds,
            )
            return
        if task.status == STATUS_PENDING:
            task = self.workflow.store.claim(task_id)
            if task is None:
                return
        if task.status != STATUS_PROCESSING:
            return
        self.workflow.store.mark_failed(task.id, error)
        updated = self.workflow.store.get(task.id)
        attempts = updated.attempts if updated is not None else task.attempts
        self._metadata_repository().schedule_retry(
            task.id,
            attempts=attempts,
            error=error,
            max_attempts=self.max_attempts,
            base_seconds=self.retry_base_seconds,
            max_seconds=self.retry_max_seconds,
        )

    def health(self) -> dict:
        stats = dict(getattr(self, "_listener_stats", {}))
        return {
            "allowed_chats": list(self.allowed_chats),
            "registered_chats": dict(self.registered_chats),
            "bot_names": list(self._effective_bot_names()),
            "listener_dispatch": "synchronous_persistence",
            "listener_stats": stats,
            "last_listener_message_at": getattr(
                self,
                "_last_listener_message_at",
                None,
            ),
            "last_persisted_task_at": getattr(
                self,
                "_last_persisted_task_at",
                None,
            ),
            "dry_run": self.dry_run,
        }
