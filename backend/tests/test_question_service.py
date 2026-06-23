import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ai_ta_bot.application import QuestionService
from ai_ta_bot.domain import HandRaiseTriggerPolicy
from ai_ta_bot.persistence import (
    ConversationRepository,
    TaskMetadataRepository,
)


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

    def test_prepares_mention_and_quote_tasks_from_original_content(self):
        with tempfile.TemporaryDirectory() as directory:
            conversations = ConversationRepository(Path(directory) / "state.db")
            generator = FakeAnswerGenerator()
            service = QuestionService(
                FakeCourseManager(),
                generator,
                conversations,
                HandRaiseTriggerPolicy(),
            )
            tasks = (
                (
                    SimpleNamespace(
                        id=2,
                        chat_name="测试群",
                        sender="张三",
                        content="@ThalesZhen\u2005晚餐怎么搭配",
                        marker="@机器人",
                    ),
                    "晚餐怎么搭配",
                ),
                (
                    SimpleNamespace(
                        id=3,
                        chat_name="测试群",
                        sender="李四",
                        content="能再具体一点吗",
                        marker="引用机器人",
                    ),
                    "能再具体一点吗",
                ),
            )

            for task, expected in tasks:
                with self.subTest(marker=task.marker):
                    prepared = service.prepare(task)
                    self.assertEqual(prepared.question, expected)

    def test_quote_context_is_passed_to_answer_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.db"
            conversations = ConversationRepository(state_path)
            metadata = TaskMetadataRepository(state_path)
            metadata.save_context(
                4,
                trigger_type="quote",
                quote_nickname="ThalesZhen",
                quote_content="白居易生于772年，晚年号香山居士。",
            )
            generator = FakeAnswerGenerator()
            service = QuestionService(
                FakeCourseManager(),
                generator,
                conversations,
                HandRaiseTriggerPolicy(),
                metadata,
            )
            task = SimpleNamespace(
                id=4,
                chat_name="测试群",
                sender="张三",
                content="你说的对吗？",
                marker="引用机器人",
            )

            prepared = service.prepare(task)

            self.assertEqual(prepared.question, "你说的对吗？")
            answer_question = generator.calls[0]["question"]
            self.assertIn("白居易生于772年", answer_question)
            self.assertIn("用户当前追问：你说的对吗？", answer_question)


if __name__ == "__main__":
    unittest.main()
