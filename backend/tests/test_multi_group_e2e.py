import gc
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from wxauto4 import WxResponse
from ai_ta_bot.application import BotRunner, QuestionService
from ai_ta_bot.configuration import CourseManager
from ai_ta_bot.domain import HandRaiseTriggerPolicy
from ai_ta_bot.integrations import WeChatGateway
from ai_ta_bot.persistence import (
    ConversationRepository,
    ReliableReplyTaskStore,
)


ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("项目研究", "每日饮食打卡🍽️")


class FakeChat:
    def __init__(self, name):
        self.who = name

    def ChatInfo(self):
        return {"chat_name": self.who, "chat_type": "group"}


class FakeWx:
    def __init__(self):
        self.windows = {}
        self.stopped = False

    def AddListenChat(self, name, callback):
        chat = FakeChat(name)
        self.windows[name] = (chat, callback)
        return chat

    def StopListening(self):
        self.stopped = True


class FakeWorkflow:
    def __init__(self, path):
        self.store = ReliableReplyTaskStore(path)
        self.replies = []

    def reply(self, task_id, reply_text):
        task = self.store.claim(task_id)
        if task is None:
            return WxResponse.failure("task unavailable")
        self.replies.append((task.chat_name, reply_text))
        self.store.mark_replied(task.id, reply_text)
        return WxResponse.success("ok")


class FakeAnswerGenerator:
    def __init__(self):
        self.calls = []

    def answer(self, question, runtime, history, sender="", group_name=""):
        self.calls.append((group_name, runtime.bot.id, question))
        return f"{runtime.bot.id}:{question}"


class MultiGroupEndToEndTests(unittest.TestCase):
    def test_two_groups_route_to_separate_bots_and_reply_to_origin_group(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.db"
            manager = CourseManager()
            manager.load(ROOT / "config" / "bot.yaml")
            manager.restrict_to_groups(GROUPS)
            generator = FakeAnswerGenerator()
            workflow = FakeWorkflow(state_path)
            wx = FakeWx()
            trigger = HandRaiseTriggerPolicy()
            gateway = WeChatGateway(
                allowed_chats=GROUPS,
                db_path=state_path,
                trigger_policy=trigger,
                dry_run=False,
                wx=wx,
                workflow=workflow,
            )
            service = QuestionService(
                manager,
                generator,
                ConversationRepository(state_path),
                trigger,
            )
            health_path = Path(directory) / "health.json"
            runner = BotRunner(
                gateway,
                service,
                group_worker_count=2,
                health_path=health_path,
            )
            gateway.start()

            questions = {
                "项目研究": "这个项目靠谱吗",
                "每日饮食打卡🍽️": "这顿饭搭配怎么样",
            }
            for index, group in enumerate(GROUPS, start=1):
                chat, callback = wx.windows[group]
                callback(
                    SimpleNamespace(
                        content=f"#举手 {questions[group]}",
                        attr="friend",
                        sender=f"用户{index}",
                        id=(index,),
                        hash=f"hash-{index}",
                        type="text",
                    ),
                    chat,
                )

            self.assertEqual(runner.run_once(), 2)
            self.assertEqual(
                set(generator.calls),
                {
                    ("项目研究", "fuye-assistant", "这个项目靠谱吗"),
                    ("每日饮食打卡🍽️", "food-assistant", "这顿饭搭配怎么样"),
                },
            )
            self.assertEqual(
                set(workflow.replies),
                {
                    ("项目研究", "fuye-assistant:这个项目靠谱吗"),
                    ("每日饮食打卡🍽️", "food-assistant:这顿饭搭配怎么样"),
                },
            )

            callback, other_chat = wx.windows["项目研究"][1], FakeChat("其他群")
            callback(
                SimpleNamespace(
                    content="#举手 不应处理",
                    attr="friend",
                    sender="其他用户",
                ),
                other_chat,
            )
            self.assertEqual(len(workflow.store.list()), 2)

            runner._write_health("running")
            health_text = health_path.read_text(encoding="utf-8")
            self.assertIn('"status": "running"', health_text)
            self.assertIn("项目研究", health_text)
            self.assertIn("每日饮食打卡", health_text)

            gateway.stop()
            del runner, service, gateway, workflow
            gc.collect()


if __name__ == "__main__":
    unittest.main()
