import tempfile
import unittest
from pathlib import Path

from ai_ta_bot.persistence import single_instance_lock


class ProcessLockTests(unittest.TestCase):
    def test_rejects_second_instance_for_same_lock_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bot.lock"
            with single_instance_lock(path):
                with self.assertRaisesRegex(RuntimeError, "拒绝重复启动"):
                    with single_instance_lock(path):
                        pass


if __name__ == "__main__":
    unittest.main()
