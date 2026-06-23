import unittest
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace

from wxauto4 import WxResponse
from ai_ta_bot.domain import HandRaiseTriggerPolicy
from ai_ta_bot.integrations.wechat_gateway import WeChatGateway
from ai_ta_bot.persistence import (
    ReliableReplyTaskStore,
    TaskMetadataRepository,
)


class FakeStore:
    def __init__(self):
        self.calls = []

    def enqueue(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=1,
            chat_name=kwargs["chat_name"],
            sender=kwargs["sender"],
        )


class FakeChat:
    def __init__(self, name="测试群", chat_type="group"):
        self.who = name
        self._info = {"chat_name": name, "chat_type": chat_type}

    def ChatInfo(self):
        return self._info


class FakeChatApi:
    def exists(self):
        return True


class QueuedChat(FakeChat):
    def __init__(self, name, messages):
        super().__init__(name)
        self._api = FakeChatApi()
        self.messages = list(messages)

    def GetNewMessage(self):
        messages, self.messages = self.messages, []
        return messages


class FakeWx:
    def __init__(self, actual_names=None):
        self.actual_names = actual_names or {}
        self.nickname = "微信"
        self.callbacks = {}
        self.stopped = False

    def AddListenChat(self, name, callback):
        actual = self.actual_names.get(name, name)
        chat = FakeChat(actual)
        self.callbacks[name] = (callback, chat)
        return chat

    def StopListening(self):
        self.stopped = True


class ReliableFakeWx(FakeWx):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages
        self.listen = {}
        self._lock = threading.RLock()

    def _get_listen_messages(self):
        raise AssertionError("original async dispatcher should be replaced")

    def AddListenChat(self, name, callback):
        chat = QueuedChat(name, self.messages)
        self.callbacks[name] = (callback, chat)
        self.listen[name] = (chat, callback)
        return chat

    def RemoveListenChat(self, name):
        self.listen.pop(name, None)


class DeliveryChat(FakeChat):
    def __init__(self, name="测试群", *, visible_after_send=True):
        super().__init__(name)
        self.messages = []
        self.visible_after_send = visible_after_send
        self.plain_sends = []

    def SendMsg(self, text):
        self.plain_sends.append(text)
        if self.visible_after_send:
            self.messages.append(SimpleNamespace(content=text))
        return WxResponse.success("sent")

    def GetAllMessage(self):
        return list(self.messages)


class FakeLocator:
    def __init__(self, response, chat=None):
        self.response = response
        self.chat = chat
        self.calls = []

    def reply(self, task, answer):
        self.calls.append((task.id, answer))
        if self.response and self.chat is not None:
            self.chat.messages.append(SimpleNamespace(content=answer))
        return self.response


class WeChatGatewayCallbackTests(unittest.TestCase):
    def make_gateway(self):
        gateway = WeChatGateway.__new__(WeChatGateway)
        gateway.allowed_chats = ("测试群",)
        gateway.trigger_policy = HandRaiseTriggerPolicy()
        gateway.allow_self = False
        gateway.bot_names = ("ThalesZhen",)
        gateway.wx = SimpleNamespace(nickname="微信")
        gateway.workflow = SimpleNamespace(store=FakeStore())
        gateway.db_path = "unused.db"
        return gateway

    def test_only_enqueues_strict_hand_raise_prefix(self):
        gateway = self.make_gateway()
        ordinary = SimpleNamespace(
            content="普通聊天里提到#举手",
            attr="friend",
            sender="张三",
        )
        hand_raise = SimpleNamespace(
            content="#举手 这个项目靠谱吗",
            attr="friend",
            sender="张三",
            id=(1, 2, 3),
            hash="hash",
            type="text",
        )

        self.assertIsNone(gateway._listener_callback(ordinary, FakeChat()))
        task = gateway._listener_callback(hand_raise, FakeChat())

        self.assertEqual(task.chat_name, "测试群")
        self.assertEqual(len(gateway.workflow.store.calls), 1)

    def test_enqueues_message_mentioning_bot_and_preserves_original_text(self):
        gateway = self.make_gateway()
        message = SimpleNamespace(
            content="@ThalesZhen\u2005今天晚上吃什么",
            attr="friend",
            sender="张三",
            id="mention-id",
            hash="mention-hash",
            type="text",
        )

        task = gateway._listener_callback(message, FakeChat())

        self.assertIsNotNone(task)
        call = gateway.workflow.store.calls[0]
        self.assertEqual(call["content"], message.content)
        self.assertEqual(call["marker"], "@机器人")

    def test_enqueues_quote_replying_to_bot(self):
        gateway = self.make_gateway()
        message = SimpleNamespace(
            content="能再具体一点吗",
            attr="friend",
            sender="张三",
            id="quote-id",
            hash="quote-hash",
            type="quote",
            quote_nickname="ThalesZhen",
            quote_content="机器人之前的回答",
        )

        task = gateway._listener_callback(message, FakeChat())

        self.assertIsNotNone(task)
        call = gateway.workflow.store.calls[0]
        self.assertEqual(call["content"], "能再具体一点吗")
        self.assertEqual(call["marker"], "引用机器人")

    def test_rejects_mentions_and_quotes_not_targeting_bot(self):
        gateway = self.make_gateway()
        messages = (
            SimpleNamespace(
                content="@其他人\u2005你怎么看",
                attr="friend",
                sender="张三",
                type="text",
            ),
            SimpleNamespace(
                content="你怎么看",
                attr="friend",
                sender="张三",
                type="quote",
                quote_nickname="其他人",
            ),
        )

        for message in messages:
            with self.subTest(content=message.content):
                self.assertIsNone(
                    gateway._listener_callback(message, FakeChat())
                )
        self.assertEqual(gateway.workflow.store.calls, [])

    def test_rejects_non_allowlisted_chat(self):
        gateway = self.make_gateway()
        message = SimpleNamespace(
            content="#举手 测试",
            attr="friend",
            sender="张三",
        )
        self.assertIsNone(
            gateway._listener_callback(message, FakeChat(name="其他群"))
        )

    def test_registers_each_allowed_group_as_a_separate_window(self):
        workflow = SimpleNamespace(store=FakeStore())
        wx = FakeWx()
        gateway = WeChatGateway(
            allowed_chats=("群A", "群B"),
            db_path="unused.db",
            trigger_policy=HandRaiseTriggerPolicy(),
            dry_run=True,
            wx=wx,
            workflow=workflow,
        )

        gateway.start()

        self.assertEqual(set(wx.callbacks), {"群A", "群B"})
        self.assertEqual(gateway.registered_chats, {"群A": "群A", "群B": "群B"})

    def test_bound_group_callback_ignores_unstable_chat_type(self):
        gateway = self.make_gateway()
        gateway.allowed_chats = ("测试群",)
        message = SimpleNamespace(
            content="#举手 今天晚上吃什么",
            attr="friend",
            sender="张三",
            id="unstable-chat-type",
            hash="unstable-chat-type-hash",
            type="text",
        )

        task = gateway._listener_callback(
            message,
            FakeChat(chat_type="friend"),
            expected_chat="测试群",
        )

        self.assertIsNotNone(task)
        self.assertEqual(task.chat_name, "测试群")

    def test_reliable_dispatch_persists_burst_synchronously_without_executor(self):
        messages = [
            SimpleNamespace(
                content=f"@ThalesZhen\u2005连续问题{i}",
                attr="friend",
                sender=f"用户{i}",
                id=f"message-{i}",
                hash=f"hash-{i}",
                type="text",
            )
            for i in range(100)
        ]
        store = FakeStore()
        wx = ReliableFakeWx(messages)
        gateway = WeChatGateway(
            allowed_chats=("测试群",),
            db_path="unused.db",
            trigger_policy=HandRaiseTriggerPolicy(),
            dry_run=True,
            bot_names=("ThalesZhen",),
            wx=wx,
            workflow=SimpleNamespace(store=store),
        )

        gateway.start()
        wx._get_listen_messages()

        self.assertEqual(len(store.calls), 100)
        self.assertEqual(
            gateway.health()["listener_dispatch"],
            "synchronous_persistence",
        )
        self.assertEqual(
            gateway.health()["listener_stats"]["tasks_persisted"],
            100,
        )

    def test_failed_persistence_is_journaled_and_recovered(self):
        class FlakyStore(FakeStore):
            def __init__(self):
                super().__init__()
                self.failures_remaining = 3

            def enqueue(self, **kwargs):
                if self.failures_remaining:
                    self.failures_remaining -= 1
                    raise RuntimeError("database temporarily locked")
                return super().enqueue(**kwargs)

        with tempfile.TemporaryDirectory() as directory:
            gateway = self.make_gateway()
            gateway.db_path = Path(directory) / "state.db"
            gateway._listener_recovery_path = (
                Path(directory) / "listener_recovery.jsonl"
            )
            gateway._listener_recovery_lock = threading.Lock()
            store = FlakyStore()
            gateway.workflow = SimpleNamespace(store=store)
            message = SimpleNamespace(
                content="@ThalesZhen\u2005需要恢复的问题",
                attr="friend",
                sender="张三",
                id="recover-id",
                hash="recover-hash",
                type="text",
            )

            with self.assertRaisesRegex(RuntimeError, "已进入恢复队列"):
                gateway._listener_callback(message, FakeChat())

            self.assertTrue(gateway._listener_recovery_path.exists())
            self.assertEqual(gateway._recover_listener_events(), 1)
            self.assertFalse(gateway._listener_recovery_path.exists())
            self.assertEqual(len(store.calls), 1)

    def test_quote_failure_falls_back_and_marks_replied_only_after_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.db"
            store = ReliableReplyTaskStore(state_path)
            chat = DeliveryChat()
            locator = FakeLocator(WxResponse.failure("quote unavailable"))
            workflow = SimpleNamespace(store=store, locator=locator)
            metadata = TaskMetadataRepository(state_path)
            gateway = WeChatGateway(
                allowed_chats=("测试群",),
                db_path=state_path,
                trigger_policy=HandRaiseTriggerPolicy(),
                dry_run=False,
                wx=SimpleNamespace(nickname="微信"),
                workflow=workflow,
                task_metadata=metadata,
                send_verify_timeout=0.2,
                send_verify_interval=0.01,
            )
            gateway._listen_windows["测试群"] = chat
            task = store.enqueue(
                chat_name="测试群",
                sender="张三",
                content="#举手 测试",
                marker="#举手",
                message_id="fallback-id",
            )

            response = gateway.reply(task.id, "最终回答")

            self.assertTrue(response)
            self.assertEqual(chat.plain_sends, ["最终回答"])
            self.assertEqual(store.get(task.id).status, "replied")
            task_metadata = metadata.get(task.id)
            self.assertEqual(task_metadata["phase"], "replied")
            self.assertEqual(task_metadata["send_mode"], "fallback")
            self.assertIsNotNone(task_metadata["verified_at"])

    def test_unverified_send_becomes_retryable_then_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.db"
            store = ReliableReplyTaskStore(state_path)
            chat = DeliveryChat(visible_after_send=False)
            workflow = SimpleNamespace(
                store=store,
                locator=FakeLocator(WxResponse.failure("quote unavailable")),
            )
            metadata = TaskMetadataRepository(state_path)
            gateway = WeChatGateway(
                allowed_chats=("测试群",),
                db_path=state_path,
                trigger_policy=HandRaiseTriggerPolicy(),
                dry_run=False,
                wx=SimpleNamespace(nickname="微信"),
                workflow=workflow,
                task_metadata=metadata,
                max_attempts=3,
                retry_base_seconds=0.1,
                retry_max_seconds=0.1,
                send_verify_timeout=0.05,
                send_verify_interval=0.01,
            )
            gateway._listen_windows["测试群"] = chat
            task = store.enqueue(
                chat_name="测试群",
                sender="张三",
                content="#举手 测试重试",
                marker="#举手",
                message_id="retry-id",
            )

            first = gateway.reply(task.id, "重试回答")

            self.assertFalse(first)
            self.assertEqual(store.get(task.id).status, "failed")
            self.assertEqual(metadata.get(task.id)["phase"], "retry_wait")
            self.assertEqual(gateway.pending_tasks(), [])

            import time

            time.sleep(0.12)
            self.assertEqual([item.id for item in gateway.pending_tasks()], [task.id])
            chat.visible_after_send = True

            second = gateway.reply(task.id, "重试回答")

            self.assertTrue(second)
            self.assertEqual(store.get(task.id).status, "replied")
            self.assertEqual(store.get(task.id).attempts, 2)

    def test_rejects_wrong_window_and_rolls_back_all_listeners(self):
        gateway = WeChatGateway(
            allowed_chats=("群A", "群B"),
            db_path="unused.db",
            trigger_policy=HandRaiseTriggerPolicy(),
            dry_run=True,
            wx=FakeWx(actual_names={"群B": "其他群"}),
            workflow=SimpleNamespace(store=FakeStore()),
        )

        with self.assertRaisesRegex(RuntimeError, "监听窗口群名不匹配"):
            gateway.start()

        self.assertTrue(gateway.wx.stopped)
        self.assertEqual(gateway.registered_chats, {})


if __name__ == "__main__":
    unittest.main()
