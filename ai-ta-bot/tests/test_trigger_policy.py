import unittest

from domain import HandRaiseTriggerPolicy


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


if __name__ == "__main__":
    unittest.main()
