import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_ta_bot.persistence import TaskMetadataRepository


class TaskMetadataRepositoryTests(unittest.TestCase):
    def test_saves_quote_context_and_delivery_phases(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = TaskMetadataRepository(
                Path(directory) / "state.db"
            )
            repository.save_context(
                1,
                trigger_type="quote",
                quote_nickname="ThalesZhen",
                quote_content="之前的机器人回答",
            )
            repository.set_phase(
                1,
                "generated",
                generated_answer="生成后的回答",
            )
            repository.set_phase(
                1,
                "replied",
                send_mode="fallback",
                verified=True,
            )

            metadata = repository.get(1)

            self.assertEqual(metadata["quote_nickname"], "ThalesZhen")
            self.assertEqual(metadata["quote_content"], "之前的机器人回答")
            self.assertEqual(metadata["generated_answer"], "生成后的回答")
            self.assertEqual(metadata["phase"], "replied")
            self.assertEqual(metadata["send_mode"], "fallback")
            self.assertIsNotNone(metadata["verified_at"])

    def test_retry_schedule_uses_backoff_and_dead_letter_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = TaskMetadataRepository(
                Path(directory) / "state.db"
            )

            phase = repository.schedule_retry(
                2,
                attempts=1,
                error="temporary",
                max_attempts=3,
                base_seconds=5,
                max_seconds=60,
            )

            self.assertEqual(phase, "retry_wait")
            self.assertFalse(
                repository.retry_due(
                    2,
                    now=datetime.now(timezone.utc),
                )
            )
            self.assertTrue(
                repository.retry_due(
                    2,
                    now=datetime.now(timezone.utc) + timedelta(seconds=6),
                )
            )

            phase = repository.schedule_retry(
                2,
                attempts=3,
                error="permanent",
                max_attempts=3,
                base_seconds=5,
                max_seconds=60,
            )

            self.assertEqual(phase, "dead_letter")
            self.assertFalse(repository.retry_due(2))


if __name__ == "__main__":
    unittest.main()
