"""Long-running task worker for the WeChat bot."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class BotRunner:
    def __init__(self, gateway, question_service, worker_interval: float = 0.5):
        self.gateway = gateway
        self.question_service = question_service
        self.worker_interval = max(0.1, worker_interval)
        self._running = False

    def start(self) -> None:
        self.gateway.start()
        self._running = True
        logger.info("任务 worker 已启动")
        try:
            while self._running:
                processed = self.run_once()
                if processed == 0:
                    time.sleep(self.worker_interval)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            self.stop()

    def stop(self) -> None:
        self._running = False
        self.gateway.stop()

    def run_once(self) -> int:
        tasks = self.gateway.pending_tasks()
        for task in tasks:
            try:
                prepared = self.question_service.prepare(task)
                response = self.gateway.reply(task.id, prepared.answer)
                if not response:
                    raise RuntimeError(
                        response.get("message") or "微信回复失败"
                    )
                self.question_service.record_success(prepared)
                logger.info(
                    "任务处理完成: task=%s chat=%s sender=%s",
                    task.id,
                    task.chat_name,
                    task.sender,
                )
            except Exception as exc:
                logger.exception("任务处理失败: task=%s", task.id)
                self.gateway.mark_failed(task.id, str(exc))
        return len(tasks)
