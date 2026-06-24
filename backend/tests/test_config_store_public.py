import unittest
from unittest.mock import patch

from ai_ta_bot import config_store


class PublicConfigTests(unittest.TestCase):
    def test_public_config_removes_cloud_internal_fields(self):
        result = config_store.public_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "资料库",
                "provider": "aliyun_bailian",
                "workspaceId": "workspace-secret",
                "indexId": "index-secret",
                "indexJobId": "job-secret",
                "indexStatus": "COMPLETED",
                "documentIds": ["file-1", "file-2"],
            }],
        })

        item = result["knowledgeBases"][0]
        self.assertTrue(item["configured"])
        self.assertTrue(item["canRefreshStatus"])
        self.assertEqual(item["documentCount"], 2)
        for field in (
            config_store.INTERNAL_KNOWLEDGE_FIELDS - {"indexStatus"}
        ):
            self.assertNotIn(field, item)

    def test_merge_public_config_preserves_server_owned_fields(self):
        existing = {
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "旧名称",
                "provider": "aliyun_bailian",
                "workspaceId": "workspace-secret",
                "indexId": "index-secret",
                "indexJobId": "job-secret",
                "documentIds": ["file-1"],
            }],
        }
        payload = {
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "新名称",
                "workspaceId": "browser-injected",
                "indexId": "browser-injected",
            }],
        }

        merged = config_store.merge_public_config(payload, existing)
        item = merged["knowledgeBases"][0]
        self.assertEqual(item["name"], "新名称")
        self.assertEqual(item["workspaceId"], "workspace-secret")
        self.assertEqual(item["indexId"], "index-secret")
        self.assertEqual(item["indexJobId"], "job-secret")
        self.assertEqual(item["documentIds"], ["file-1"])

    def test_new_knowledge_base_uses_platform_workspace(self):
        with patch(
            "ai_ta_bot.config.ALIYUN_BAILIAN_WORKSPACE_ID",
            "platform-workspace",
        ):
            merged = config_store.merge_public_config(
                {"knowledgeBases": [{"id": "kb-new", "name": "新资料库"}]},
                {"knowledgeBases": []},
            )

        self.assertEqual(
            merged["knowledgeBases"][0]["workspaceId"],
            "platform-workspace",
        )


if __name__ == "__main__":
    unittest.main()
