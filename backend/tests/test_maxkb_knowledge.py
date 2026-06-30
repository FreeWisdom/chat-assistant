"""Tests for MaxKB direct-answer provider integration."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_ta_bot.config_store import (
    SUPPORTED_PROVIDERS,
    merge_public_config,
    normalize_config,
    public_config,
    validate_config,
)
from ai_ta_bot.configuration.models import KnowledgeBase
from ai_ta_bot.knowledge.answer_generator import RAGEngine
from ai_ta_bot.knowledge.factory import create_knowledge_client, create_knowledge_manager
from ai_ta_bot.knowledge.maxkb_knowledge import MaxKBKnowledgeClient, MaxKBKnowledgeManager


def _maxkb_kb(**overrides):
    defaults = {
        "id": "kb-mx-1",
        "name": "Test MaxKB App",
        "description": "test",
        "provider": "maxkb",
        "maxkb_app_id": "app-123",
        "priority": 10,
    }
    defaults.update(overrides)
    return KnowledgeBase(**defaults)


def _runtime(kb):
    return SimpleNamespace(
        group="测试群",
        bot=SimpleNamespace(
            name="测试机器人",
            role="回答问题",
            identity_prompt="",
            responsibilities=["回答当前问题"],
        ),
        style=SimpleNamespace(
            tone="简短",
            max_chars=180,
            emoji_policy="少用",
            avoid_words=[],
            examples=[],
        ),
        knowledge_bases=[kb],
        knowledge_base_ids=[kb.id],
    )


class MaxKBClientTests(unittest.TestCase):
    def make_client(self, **kwargs):
        return MaxKBKnowledgeClient(
            base_url="http://127.0.0.1:8080",
            api_key="agent-key",
            **kwargs,
        )

    def test_validate_rejects_missing_app_id(self):
        client = self.make_client()
        with self.assertRaises(ValueError) as ctx:
            client.validate([_maxkb_kb(maxkb_app_id="")])
        self.assertIn("maxkbAppId", str(ctx.exception))

    def test_answer_uses_openai_compatible_endpoint(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "MaxKB answer"},
            }],
        }
        mock_session.post.return_value = mock_resp

        client = self.make_client(http_session=mock_session)
        answer = client.answer([_maxkb_kb()], "hello")

        self.assertEqual(answer, "MaxKB answer")
        url = mock_session.post.call_args.args[0]
        self.assertEqual(
            url,
            "http://127.0.0.1:8080/chat/api/app-123/chat/completions",
        )
        payload = mock_session.post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][-1]["content"], "hello")
        self.assertFalse(payload["stream"])

    def test_base_url_may_already_include_chat_api_path(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_session.post.return_value = mock_resp

        client = MaxKBKnowledgeClient(
            base_url="http://127.0.0.1:8080/chat/api",
            api_key="agent-key",
            http_session=mock_session,
        )
        client.answer([_maxkb_kb()], "hello")

        self.assertEqual(
            mock_session.post.call_args.args[0],
            "http://127.0.0.1:8080/chat/api/app-123/chat/completions",
        )


class MaxKBFactoryAndConfigTests(unittest.TestCase):
    def test_factory_creates_maxkb_provider(self):
        self.assertEqual(create_knowledge_client("maxkb").provider, "maxkb")
        self.assertIsInstance(create_knowledge_manager("maxkb"), MaxKBKnowledgeManager)

    def test_config_store_supports_maxkb(self):
        self.assertIn("maxkb", SUPPORTED_PROVIDERS)
        config = normalize_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "MaxKB",
                "provider": "maxkb",
                "maxkbAppId": "app-123",
            }],
        })
        item = config["knowledgeBases"][0]
        self.assertEqual(item["provider"], "maxkb")
        self.assertEqual(item["maxkbAppId"], "app-123")
        pub = public_config(config)["knowledgeBases"][0]
        self.assertEqual(pub["provider"], "maxkb")
        self.assertEqual(pub["providerLabel"], "MaxKB")
        self.assertTrue(pub["configured"])

    def test_bound_maxkb_requires_app_id(self):
        config = {
            "botProfiles": [{"id": "bot-1", "name": "Bot", "styleId": "s1"}],
            "styles": [{"id": "s1", "name": "Style", "maxChars": 100}],
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "MaxKB",
                "provider": "maxkb",
                "maxkbAppId": "",
            }],
            "bindings": [{
                "group": "test",
                "botId": "bot-1",
                "knowledgeBaseIds": ["kb-1"],
            }],
        }
        errors = validate_config(normalize_config(config))
        self.assertTrue(any("maxkbAppId" in item for item in errors), errors)

    def test_merge_public_allows_maxkb_app_id_update(self):
        existing = normalize_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "MaxKB",
                "provider": "maxkb",
                "maxkbAppId": "old-app",
            }],
        })
        merged = merge_public_config({
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "MaxKB",
                "provider": "maxkb",
                "maxkbAppId": "new-app",
            }],
        }, existing)

        self.assertEqual(merged["knowledgeBases"][0]["maxkbAppId"], "new-app")


class RAGEngineMaxKBTests(unittest.TestCase):
    def test_maxkb_provider_returns_direct_answer_without_local_llm(self):
        kb = _maxkb_kb()
        knowledge_client = MagicMock()
        knowledge_client.provider = "maxkb"
        knowledge_client.answer.return_value = "MaxKB direct answer"
        engine = RAGEngine(
            client=None,
            knowledge_client=knowledge_client,
            web_searcher=MagicMock(),
            question_router=MagicMock(),
        )

        answer = engine.answer("问题", _runtime(kb))

        self.assertEqual(answer, "MaxKB direct answer")
        knowledge_client.answer.assert_called_once()
        engine.question_router.classify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
