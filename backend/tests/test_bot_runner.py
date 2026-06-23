import json
from pathlib import Path
import tempfile
import unittest
import threading
from types import SimpleNamespace

from ai_ta_bot.application import BotRunner


class FakeGateway:
    def __init__(self, tasks, reply_result=True):
        self.tasks = tasks
        self.reply_result = reply_result
        self.replies = []
        self.failures = []

    def pending_tasks(self):
        return list(self.tasks)

    def reply(self, task_id, answer):
        self.replies.append((task_id, answer))
        return self.reply_result

    def mark_failed(self, task_id, error):
        self.failures.append((task_id, error))

    def stop(self):
        return None


class FakeQuestionService:
    def __init__(self, fail=False):
        self.fail = fail
        self.recorded = []

    def prepare(self, task):
        if self.fail:
            raise RuntimeError("prepare failed")
        return SimpleNamespace(
            task_id=task.id,
            answer="answer",
            group_name=task.chat_name,
            sender=task.sender,
        )

    def record_success(self, prepared):
        self.recorded.append(prepared)


class BotRunnerTests(unittest.TestCase):
    def test_startup_failure_is_preserved_in_health_file(self):
        class StartupFailureGateway:
            registered_chats = {}

            def start(self):
                raise RuntimeError("window unavailable")

            def stop(self):
                return None

            def health(self):
                return {
                    "allowed_chats": ["项目研究"],
                    "registered_chats": {},
                    "dry_run": False,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            health_path = Path(temp_dir) / "bot_health.json"
            runner = BotRunner(
                StartupFailureGateway(),
                FakeQuestionService(),
                health_path=health_path,
            )

            with self.assertRaisesRegex(RuntimeError, "window unavailable"):
                runner.start()

            health = json.loads(health_path.read_text(encoding="utf-8"))
            self.assertEqual(health["status"], "failed")
            self.assertEqual(health["error"], "window unavailable")

    def test_records_history_only_after_reply_success(self):
        task = SimpleNamespace(id=1, chat_name="群", sender="张三")
        gateway = FakeGateway([task])
        service = FakeQuestionService()
        runner = BotRunner(gateway, service)

        self.assertEqual(runner.run_once(), 1)
        self.assertEqual(gateway.replies, [(1, "answer")])
        self.assertEqual(len(service.recorded), 1)
        self.assertEqual(gateway.failures, [])

    def test_marks_task_failed_when_preparation_fails(self):
        task = SimpleNamespace(id=2, chat_name="群", sender="张三")
        gateway = FakeGateway([task])
        runner = BotRunner(gateway, FakeQuestionService(fail=True))

        runner.run_once()

        self.assertEqual(gateway.replies, [])
        self.assertEqual(gateway.failures[0][0], 2)

    def test_processes_different_groups_in_parallel_and_same_group_in_order(self):
        tasks = [
            SimpleNamespace(id=1, chat_name="群A", sender="甲"),
            SimpleNamespace(id=2, chat_name="群A", sender="乙"),
            SimpleNamespace(id=3, chat_name="群B", sender="丙"),
        ]
        gateway = FakeGateway(tasks)
        barrier = threading.Barrier(2)

        class ParallelQuestionService(FakeQuestionService):
            def prepare(self, task):
                barrier.wait(timeout=2)
                return super().prepare(task)

        runner = BotRunner(
            gateway,
            ParallelQuestionService(),
            group_worker_count=2,
        )

        self.assertEqual(runner.run_once(), 2)
        self.assertEqual(
            {task_id for task_id, _ in gateway.replies},
            {1, 3},
        )
        self.assertNotIn(2, [task_id for task_id, _ in gateway.replies])


if __name__ == "__main__":
    unittest.main()
