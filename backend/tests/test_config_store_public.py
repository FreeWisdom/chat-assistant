import unittest

from ai_ta_bot import config_store


class PublicConfigTests(unittest.TestCase):
    def test_public_config_shows_maxkb_app_id(self):
        result = config_store.public_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "资料库",
                "provider": "maxkb",
                "maxkbAppId": "app-123",
            }],
        })

        item = result["knowledgeBases"][0]
        self.assertTrue(item["configured"])
        self.assertEqual(item["provider"], "maxkb")
        self.assertEqual(item["maxkbAppId"], "app-123")
        self.assertEqual(item["providerLabel"], "MaxKB")

    def test_public_config_hides_maxkb_app_id_for_non_maxkb(self):
        """All KBs are maxkb now, but test the defensive behaviour."""
        result = config_store.public_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "资料库",
                "provider": "maxkb",
                "maxkbAppId": "",
            }],
        })

        item = result["knowledgeBases"][0]
        self.assertFalse(item["configured"])

    def test_merge_public_config_preserves_maxkb_fields(self):
        existing = {
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "旧名称",
                "provider": "maxkb",
                "maxkbAppId": "app-secret",
            }],
        }
        payload = {
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "新名称",
                "maxkbAppId": "browser-injected",
            }],
        }

        merged = config_store.merge_public_config(payload, existing)
        item = merged["knowledgeBases"][0]
        self.assertEqual(item["name"], "新名称")
        self.assertEqual(item["maxkbAppId"], "browser-injected")
        self.assertEqual(item["provider"], "maxkb")

    def test_new_knowledge_base_defaults_to_maxkb(self):
        merged = config_store.merge_public_config(
            {"knowledgeBases": [{"id": "kb-new", "name": "新资料库"}]},
            {"knowledgeBases": []},
        )

        self.assertEqual(
            merged["knowledgeBases"][0]["provider"],
            "maxkb",
        )


if __name__ == "__main__":
    unittest.main()
