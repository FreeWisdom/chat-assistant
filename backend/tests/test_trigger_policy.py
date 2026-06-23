import unittest
from types import SimpleNamespace

from ai_ta_bot.domain import HandRaiseTriggerPolicy


class HandRaiseTriggerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = HandRaiseTriggerPolicy()

    def test_extracts_ascii_marker_prefix(self):
        self.assertEqual(self.policy.extract("#举手 这个项目靠谱吗？"), "这个项目靠谱吗？")

    def test_extracts_full_width_marker_prefix(self):
        self.assertEqual(self.policy.extract("＃举手怎么开始"), "怎么开始")

    def test_rejects_marker_in_middle(self):
        self.assertIsNone(self.policy.extract("聊天里提到了#举手这个词"))

    def test_rejects_empty_question(self):
        self.assertIsNone(self.policy.extract("#举手"))

    def test_matches_message_mentioning_bot(self):
        match = self.policy.match_message(
            SimpleNamespace(
                content="@ThalesZhen\u2005今天有什么新闻",
                type="text",
            ),
            ("ThalesZhen",),
        )

        self.assertEqual(match.question, "今天有什么新闻")
        self.assertEqual(match.trigger_type, "mention")
        self.assertEqual(match.marker, "@机器人")

    def test_rejects_message_mentioning_someone_else(self):
        match = self.policy.match_message(
            SimpleNamespace(
                content="@其他人\u2005今天有什么新闻",
                type="text",
            ),
            ("ThalesZhen",),
        )

        self.assertIsNone(match)

    def test_matches_quote_replying_to_bot(self):
        match = self.policy.match_message(
            SimpleNamespace(
                content="这个建议能再具体一点吗",
                type="quote",
                quote_nickname="ThalesZhen",
                quote_content="上一条机器人回复",
            ),
            ("ThalesZhen",),
        )

        self.assertEqual(match.question, "这个建议能再具体一点吗")
        self.assertEqual(match.trigger_type, "quote")
        self.assertEqual(match.marker, "引用机器人")

    def test_rejects_quote_replying_to_someone_else(self):
        match = self.policy.match_message(
            SimpleNamespace(
                content="你再说说",
                type="quote",
                quote_nickname="其他人",
                quote_content="其他人的消息",
            ),
            ("ThalesZhen",),
        )

        self.assertIsNone(match)

    def test_extracts_persisted_directed_messages(self):
        self.assertEqual(
            self.policy.extract_persisted(
                "@ThalesZhen\u2005今天晚上吃什么",
                "@机器人",
            ),
            "今天晚上吃什么",
        )
        self.assertEqual(
            self.policy.extract_persisted(
                "能再展开一点吗",
                "引用机器人",
            ),
            "能再展开一点吗",
        )


if __name__ == "__main__":
    unittest.main()
