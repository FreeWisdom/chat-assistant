import unittest
from types import SimpleNamespace

from ai_ta_bot.domain import HandRaiseTriggerPolicy
from ai_ta_bot.integrations.wechat_gateway import WeChatGateway


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


class WeChatGatewayCallbackTests(unittest.TestCase):
    def make_gateway(self):
        gateway = WeChatGateway.__new__(WeChatGateway)
        gateway.allowed_chats = ("测试群",)
        gateway.trigger_policy = HandRaiseTriggerPolicy()
        gateway.allow_self = False
        gateway.workflow = SimpleNamespace(store=FakeStore())
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


if __name__ == "__main__":
    unittest.main()
