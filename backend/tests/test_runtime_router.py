import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_ta_bot.admin.services import process_manager
from ai_ta_bot.admin_app import app


def _valid_config():
    return {
        "botProfiles": [{
            "id": "bot-1",
            "name": "测试机器人",
            "styleId": "style-1",
        }],
        "styles": [{
            "id": "style-1",
            "name": "测试风格",
            "maxChars": 180,
        }],
        "knowledgeBases": [{
            "id": "kb-1",
            "name": "测试知识库",
            "provider": "aliyun_bailian",
            "workspaceId": "workspace-1",
            "indexId": "index-1",
        }],
        "bindings": [{
            "group": "项目研究",
            "botId": "bot-1",
            "knowledgeBaseIds": ["kb-1"],
        }],
        "global": {},
    }


class RuntimeRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pid_file = self.root / "runtime" / "bot.pid"
        self.log_dir = self.root / "runtime" / "logs"
        self.health_path = self.root / "runtime" / "bot_health.json"
        self.patches = [
            patch.object(process_manager, "PROJECT_ROOT", self.root),
            patch.object(process_manager, "PID_FILE", self.pid_file),
            patch.object(process_manager, "LOG_DIR", self.log_dir),
            patch.object(process_manager, "_health_path", return_value=self.health_path),
            patch.object(process_manager.config, "LLM_API_KEY", "sk-test"),
            patch.object(process_manager.config, "DRY_RUN", True),
            patch.object(process_manager.config, "LISTEN_GROUPS", ("项目研究",)),
            patch.object(process_manager.config, "BOT_MENTION_NAMES", ("测试机器人",)),
            patch.object(process_manager.config, "REQUIRE_LISTEN_GROUPS", True),
            patch.object(process_manager.config, "WEB_SEARCH_ENABLED", False),
            patch.object(process_manager.config_store, "read_config", return_value=_valid_config()),
            patch.object(process_manager.config_store, "validate_config", return_value=[]),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_runtime_health_contract_for_not_started(self):
        response = self.client.get("/api/runtime/health")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "not_started")
        self.assertFalse(payload["running"])
        self.assertIsNone(payload["pid"])
        self.assertEqual(payload["listenGroups"], ["项目研究"])
        self.assertEqual(payload["botMentionNames"], ["测试机器人"])
        self.assertIn("warnings", payload)

    def test_start_rejects_blocking_preflight_errors(self):
        with patch.object(process_manager.config, "LLM_API_KEY", ""):
            response = self.client.post(
                "/api/runtime/start",
                json={"force": False},
            )

        self.assertEqual(response.status_code, 400, response.text)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(
            payload["blockingChecks"][0]["code"],
            "MISSING_LLM_API_KEY",
        )

    def test_start_writes_pid_metadata_and_returns_contract(self):
        dummy_proc = SimpleNamespace(pid=4321)
        with (
            patch.object(
                process_manager,
                "_get_process_commandline",
                return_value="",
            ),
            patch.object(
                process_manager.subprocess,
                "Popen",
                return_value=dummy_proc,
            ) as popen,
        ):
            response = self.client.post(
                "/api/runtime/start",
                json={"force": False},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "starting")
        self.assertEqual(payload["pid"], 4321)
        self.assertTrue(payload["logFile"].startswith("runtime/logs/bot_"))
        self.assertTrue(self.pid_file.exists())
        self.assertTrue(self.log_dir.exists())
        popen.assert_called_once()

    def test_stop_refuses_unmanaged_pid(self):
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text('{"pid": 999, "logFile": "runtime/logs/bot.log"}', encoding="utf-8")
        with patch.object(
            process_manager,
            "_get_process_commandline",
            return_value="python other_script.py",
        ):
            response = self.client.post(
                "/api/runtime/stop",
                json={"force": True},
            )

        self.assertEqual(response.status_code, 400, response.text)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("不是本产品机器人进程", payload["message"])
        self.assertTrue(self.pid_file.exists())

    def test_logs_returns_redacted_tail(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / "bot_20260629_101530.log"
        log_file.write_text(
            "first\nsecret sk-1234567890abcdef\nlast\n",
            encoding="utf-8",
        )
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(
            '{"pid": 123, "logFile": "runtime/logs/bot_20260629_101530.log"}',
            encoding="utf-8",
        )

        response = self.client.get("/api/runtime/logs?limit=2")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["truncated"])
        self.assertEqual(len(payload["lines"]), 2)
        self.assertIn("sk-***", payload["lines"][0])


if __name__ == "__main__":
    unittest.main()
