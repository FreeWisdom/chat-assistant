import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_ta_bot import config
from ai_ta_bot.knowledge.answer_generator import RAGEngine
from ai_ta_bot.knowledge.question_router import (
    ROUTE_DIRECT,
    ROUTE_KNOWLEDGE,
    ROUTE_WEB,
    RouteDecision,
)


class FakeRetriever:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, knowledge_base_ids, query, top_k):
        self.queries.append((knowledge_base_ids, query, top_k))
        return list(self.results)


class FakeWebSearcher:
    def __init__(self):
        self.queries = []

    def search(self, query, max_results):
        self.queries.append((query, max_results))
        return [{
            "content": "今天的新消息和最新政策摘要",
            "source": "网页标题",
            "url": "https://example.com/source",
            "kb_name": "联网搜索",
        }]

    @staticmethod
    def is_time_sensitive(query):
        return any(word in query for word in ("最新", "今天", "近期"))


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="测试回答"))],
            usage=None,
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class FakeRouter:
    def __init__(self, route, search_query=""):
        self.decision = RouteDecision(
            route=route,
            reason="test",
            search_query=search_query,
        )
        self.calls = []

    def classify(self, question, runtime, chat_history=None):
        self.calls.append((question, runtime, chat_history))
        return self.decision


def make_runtime():
    bot = SimpleNamespace(
        name="测试机器人",
        role="回答问题",
        identity_prompt="保持准确",
        responsibilities=["回答当前问题"],
    )
    style = SimpleNamespace(
        tone="简短",
        max_chars=180,
        emoji_policy="少用",
        avoid_words=[],
        examples=[],
    )
    return SimpleNamespace(
        group="测试群",
        bot=bot,
        style=style,
        knowledge_bases=[],
        knowledge_base_ids=[],
    )


class RAGEngineWebFallbackTests(unittest.TestCase):
    def test_uses_web_search_when_local_knowledge_has_no_match(self):
        client = FakeClient()
        searcher = FakeWebSearcher()
        engine = RAGEngine(
            client=client,
            retriever=FakeRetriever([]),
            web_searcher=searcher,
            question_router=FakeRouter(
                ROUTE_WEB,
                search_query="今天 新消息",
            ),
        )

        with patch.object(config, "WEB_SEARCH_ENABLED", True):
            answer = engine.answer("今天有什么新消息", make_runtime())

        self.assertTrue(answer.startswith("测试回答"))
        self.assertEqual(len(searcher.queries), 1)
        self.assertIn("来源：", answer)
        self.assertIn("https://example.com/source", answer)
        self.assertEqual(len(client.chat.completions.calls), 1)
        system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        self.assertIn("【联网搜索结果】", system_prompt)
        self.assertIn("https://example.com/source", system_prompt)

    def test_does_not_search_web_when_local_knowledge_matches(self):
        client = FakeClient()
        searcher = FakeWebSearcher()
        engine = RAGEngine(
            client=client,
            retriever=FakeRetriever([{
                "content": "本地知识",
                "source": "local.md",
                "kb_name": "本地库",
            }]),
            web_searcher=searcher,
            question_router=FakeRouter(ROUTE_KNOWLEDGE),
        )

        with patch.object(config, "WEB_SEARCH_ENABLED", True):
            engine.answer("本地问题", make_runtime())

        self.assertEqual(searcher.queries, [])
        system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        self.assertIn("【命中的知识库资料】", system_prompt)

    def test_time_sensitive_question_searches_web_even_when_local_matches(self):
        client = FakeClient()
        searcher = FakeWebSearcher()
        engine = RAGEngine(
            client=client,
            retriever=FakeRetriever([{
                "content": "可能已经过时的本地知识",
                "source": "local.md",
                "kb_name": "本地库",
            }]),
            web_searcher=searcher,
            question_router=FakeRouter(
                ROUTE_WEB,
                search_query="最新 政策",
            ),
        )

        with patch.object(config, "WEB_SEARCH_ENABLED", True):
            answer = engine.answer("最新政策是什么", make_runtime())

        self.assertEqual(len(searcher.queries), 1)
        self.assertIn("来源：", answer)
        system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        self.assertIn("【联网搜索结果】", system_prompt)

    def test_direct_route_skips_knowledge_and_web_but_still_uses_llm(self):
        client = FakeClient()
        retriever = FakeRetriever([{
            "content": "不应读取",
            "source": "local.md",
            "kb_name": "本地库",
        }])
        searcher = FakeWebSearcher()
        engine = RAGEngine(
            client=client,
            retriever=retriever,
            web_searcher=searcher,
            question_router=FakeRouter(ROUTE_DIRECT),
        )

        answer = engine.answer("今天晚上吃什么", make_runtime())

        self.assertEqual(answer, "测试回答")
        self.assertEqual(retriever.queries, [])
        self.assertEqual(searcher.queries, [])
        self.assertEqual(len(client.chat.completions.calls), 1)
        system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        self.assertIn("可由大模型直接回答", system_prompt)
        self.assertIn("最终表达润色", system_prompt)

    def test_unrelated_web_results_are_not_prompted_or_cited(self):
        client = FakeClient()

        class IrrelevantSearcher(FakeWebSearcher):
            def search(self, query, max_results):
                self.queries.append((query, max_results))
                return [{
                    "content": "Los Angeles pedestrian accident",
                    "source": "US local news",
                    "title": "Pedestrian accident",
                    "url": "https://example.com/unrelated",
                    "kb_name": "联网搜索",
                }]

        searcher = IrrelevantSearcher()
        engine = RAGEngine(
            client=client,
            retriever=FakeRetriever([]),
            web_searcher=searcher,
            question_router=FakeRouter(
                ROUTE_WEB,
                search_query="纸尿裤事件 最新进展",
            ),
        )

        answer = engine.answer("最近纸尿裤事件的最新进展如何", make_runtime())

        self.assertEqual(answer, "测试回答")
        self.assertNotIn("来源：", answer)
        system_prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        self.assertIn("未返回与问题足够相关的结果", system_prompt)
        self.assertNotIn("https://example.com/unrelated", system_prompt)

    def test_appends_at_most_two_unique_web_sources(self):
        answer = RAGEngine._append_web_sources(
            "正文",
            [
                {"title": "来源一", "url": "https://example.com/1"},
                {"title": "重复来源", "url": "https://example.com/1"},
                {"title": "来源二", "url": "https://example.com/2"},
                {"title": "来源三", "url": "https://example.com/3"},
            ],
        )

        self.assertIn("来源一 https://example.com/1", answer)
        self.assertIn("来源二 https://example.com/2", answer)
        self.assertNotIn("https://example.com/3", answer)


if __name__ == "__main__":
    unittest.main()
