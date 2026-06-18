import tempfile
import unittest
from pathlib import Path

from ai_ta_bot.persistence import ConversationRepository


class ConversationRepositoryTests(unittest.TestCase):
    def test_history_is_isolated_by_group_and_sender(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ConversationRepository(Path(directory) / "state.db")
            repository.append("群A", "用户A", "user", "问题A")
            repository.append("群A", "用户A", "assistant", "回答A")
            repository.append("群A", "用户B", "user", "问题B")

            self.assertEqual(
                repository.recent("群A", "用户A"),
                [
                    {"role": "user", "content": "问题A"},
                    {"role": "assistant", "content": "回答A"},
                ],
            )
            self.assertEqual(
                repository.recent("群A", "用户B"),
                [{"role": "user", "content": "问题B"}],
            )
            self.assertEqual(repository.recent("群B", "用户A"), [])

    def test_history_survives_repository_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.db"
            ConversationRepository(path).append("群A", "用户A", "user", "重启前")
            recreated = ConversationRepository(path)
            self.assertEqual(
                recreated.recent("群A", "用户A"),
                [{"role": "user", "content": "重启前"}],
            )


if __name__ == "__main__":
    unittest.main()
