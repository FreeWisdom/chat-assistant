import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ai_ta_bot.application import QuestionService
from ai_ta_bot.domain import HandRaiseTriggerPolicy
from ai_ta_bot.persistence import ConversationRepository


class FakeCourseManager:
    def __init__(self):
        self.runtime = object()

    def get_course(self, group_name):
        return self.runtime if group_name == "测试群" else None


class FakeAnswerGenerator:
    def __init__(self):
        self.calls = []

    def answer(self, question, runtime, history, sender="", group_name=""):
        self.calls.append(
            {
                "question": question,
                "runtime": runtime,
                "history": history,
                "sender": sender,
                "group_name": group_name,
            }
        )
        return "测试回答"


class QuestionServiceTests(unittest.TestCase):
    def test_prepares_answer_with_per_user_history(self):
        with tempfile.TemporaryDirectory() as directory:
            conversations = ConversationRepository(Path(directory) / "state.db")
            conversations.append("测试群", "张三", "user", "上一个问题")
            generator = FakeAnswerGenerator()
            service = QuestionService(
                FakeCourseManager(),
                generator,
                conversations,
                HandRaiseTriggerPolicy(),
            )
            task = SimpleNamespace(
                id=1,
                chat_name="测试群",
                sender="张三",
                content="#举手 新问题",
            )

            prepared = service.prepare(task)

            self.assertEqual(prepared.question, "新问题")
            self.assertEqual(
                generator.calls[0]["history"],
                [{"role": "user", "content": "上一个问题"}],
            )

    def test_records_success_after_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            conversations = ConversationRepository(Path(directory) / "state.db")
            service = QuestionService(
                FakeCourseManager(),
                FakeAnswerGenerator(),
                conversations,
                HandRaiseTriggerPolicy(),
            )
            task = SimpleNamespace(
                id=1,
                chat_name="测试群",
                sender="张三",
                content="#举手 新问题",
            )
            prepared = service.prepare(task)
            service.record_success(prepared)

            self.assertEqual(
                conversations.recent("测试群", "张三"),
                [
                    {"role": "user", "content": "新问题"},
                    {"role": "assistant", "content": "测试回答"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
