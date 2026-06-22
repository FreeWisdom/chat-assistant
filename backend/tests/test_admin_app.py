import unittest

from fastapi.testclient import TestClient

from ai_ta_bot import config
from ai_ta_bot.admin_app import app


class AdminAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.sync_headers = (
            {"X-Admin-Token": config.ADMIN_SYNC_TOKEN}
            if config.ADMIN_SYNC_TOKEN
            else {}
        )

    def test_read_endpoints_are_available(self):
        for path in (
            "/api/config",
            "/api/knowledge/files",
            "/api/backups",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)

        response = self.client.get(
            "/api/sync/health",
            headers=self.sync_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_validate_endpoint_accepts_current_config(self):
        current = self.client.get("/api/config").json()["config"]
        response = self.client.post("/api/validate", json=current)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["errors"], [])


if __name__ == "__main__":
    unittest.main()
