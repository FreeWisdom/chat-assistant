import unittest
from types import SimpleNamespace

from application import BotRunner


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


if __name__ == "__main__":
    unittest.main()
