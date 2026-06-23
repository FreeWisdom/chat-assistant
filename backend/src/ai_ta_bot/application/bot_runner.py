"""Long-running task worker for the WeChat bot."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)


class BotRunner:
    """Process one task per group concurrently while preserving group order."""

    def __init__(
        self,
        gateway,
        question_service,
        worker_interval: float = 0.5,
        group_worker_count: int = 4,
        health_path: str | Path | None = None,
    ):
        self.gateway = gateway
        self.question_service = question_service
        self.worker_interval = max(0.1, worker_interval)
        self.group_worker_count = max(1, group_worker_count)
        self.health_path = Path(health_path).resolve() if health_path else None
        self._running = False
        self._executor = None
        self._health_lock = threading.Lock()

    def start(self) -> None:
        final_status = "stopped"
        failure_error = None
        self._write_health("starting")
        try:
            self.gateway.start()
            self._running = True
            self._write_health("running")
            logger.info(
                "任务 worker 已启动: groups=%s workers=%s",
                list(self.gateway.registered_chats),
                self.group_worker_count,
            )
            with ThreadPoolExecutor(
                max_workers=self.group_worker_count,
                thread_name_prefix="group-worker",
            ) as executor:
                self._executor = executor
                while self._running:
                    processed = self.run_once()
                    if processed == 0:
                        time.sleep(self.worker_interval)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as exc:
            final_status = "failed"
            failure_error = str(exc)
            raise
        finally:
            self._executor = None
            self.stop(status=final_status, error=failure_error)

    def stop(self, status: str = "stopped", error: str | None = None) -> None:
        self._running = False
        self.gateway.stop()
        extra = {"error": error} if error else {}
        self._write_health(status, **extra)

    def run_once(self) -> int:
        tasks = self.gateway.pending_tasks()
        group_heads = []
        scheduled_groups = set()
        for task in tasks:
            if task.chat_name in scheduled_groups:
                continue
            scheduled_groups.add(task.chat_name)
            group_heads.append(task)

        if not group_heads:
            return 0

        if self._executor is None:
            with ThreadPoolExecutor(
                max_workers=min(self.group_worker_count, len(group_heads)),
                thread_name_prefix="group-worker-once",
            ) as executor:
                self._wait_for_tasks(executor, group_heads)
        else:
            self._wait_for_tasks(self._executor, group_heads)
        return len(group_heads)

    def _wait_for_tasks(self, executor, tasks) -> None:
        futures = [
            executor.submit(self._process_task, task)
            for task in tasks
        ]
        for future in as_completed(futures):
            future.result()

    def _process_task(self, task) -> None:
        try:
            if hasattr(self.gateway, "mark_phase"):
                self.gateway.mark_phase(task.id, "processing")
            prepared = self.question_service.prepare(task)
            if hasattr(self.gateway, "mark_phase"):
                self.gateway.mark_phase(
                    task.id,
                    "generated",
                    answer=prepared.answer,
                )
            response = self.gateway.reply(task.id, prepared.answer)
            if not response:
                message = (
                    response.get("message")
                    if hasattr(response, "get")
                    else "微信回复失败"
                )
                raise RuntimeError(message or "微信回复失败")
            self.question_service.record_success(prepared)
            self._write_health(
                "running",
                last_task={
                    "id": task.id,
                    "chat_name": task.chat_name,
                    "sender": task.sender,
                    "result": "success",
                },
            )
            logger.info(
                "任务处理完成: task=%s chat=%s sender=%s",
                task.id,
                task.chat_name,
                task.sender,
            )
        except Exception as exc:
            logger.exception("任务处理失败: task=%s", task.id)
            self.gateway.mark_failed(task.id, str(exc))
            self._write_health(
                "running",
                last_task={
                    "id": task.id,
                    "chat_name": task.chat_name,
                    "sender": task.sender,
                    "result": "failed",
                    "error": str(exc),
                },
            )

    def _write_health(self, status: str, **extra) -> None:
        if self.health_path is None:
            return
        payload = {
            "status": status,
            "pid": os.getpid(),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **self.gateway.health(),
            **extra,
        }
        with self._health_lock:
            self.health_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.health_path.with_suffix(
                self.health_path.suffix + ".tmp"
            )
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.health_path)
