import json
import unittest
from types import SimpleNamespace

from ai_ta_bot.knowledge.question_router import (
    LLMQuestionRouter,
    ROUTE_DIRECT,
    ROUTE_KNOWLEDGE,
    ROUTE_WEB,
)


class QueueCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.contents.pop(0))
                )
            ]
        )


def make_runtime():
    kb = SimpleNamespace(
        name="饮食打卡知识库",
        description="营养搭配、热量和饮食记录",
        tags=["饮食", "营养", "热量"],
        route_examples=["这顿饭热量多少", "晚餐怎么搭配"],
    )
    return SimpleNamespace(
        group="每日饮食打卡🍽️",
        bot=SimpleNamespace(role="回答饮食问题"),
        knowledge_bases=[kb],
    )


class LLMQuestionRouterTests(unittest.TestCase):
    def test_parses_direct_route(self):
        completions = QueueCompletions([
            json.dumps({
                "route": "direct",
                "reason": "稳定生活建议",
                "search_query": "",
            }, ensure_ascii=False)
        ])
        router = LLMQuestionRouter(
            SimpleNamespace(chat=SimpleNamespace(completions=completions))
        )

        decision = router.classify("今天晚上吃什么", make_runtime())

        self.assertEqual(decision.route, ROUTE_DIRECT)
        self.assertEqual(decision.search_query, "")
        prompt = completions.calls[0]["messages"][0]["content"]
        self.assertIn("今天晚上吃什么", prompt)
        self.assertIn("direct", prompt)

    def test_parses_web_route_and_search_query(self):
        completions = QueueCompletions([
            json.dumps({
                "route": "web",
                "reason": "需要最新外部信息",
                "search_query": "杭州 今日天气",
            }, ensure_ascii=False)
        ])
        router = LLMQuestionRouter(
            SimpleNamespace(chat=SimpleNamespace(completions=completions))
        )

        decision = router.classify("今天杭州天气怎么样", make_runtime())

        self.assertEqual(decision.route, ROUTE_WEB)
        self.assertEqual(decision.search_query, "杭州 今日天气")

    def test_invalid_response_falls_back_without_misrouting_dinner_to_web(self):
        completions = QueueCompletions(["not json"])
        router = LLMQuestionRouter(
            SimpleNamespace(chat=SimpleNamespace(completions=completions))
        )

        decision = router.classify("今天晚上吃什么", make_runtime())

        self.assertEqual(decision.route, ROUTE_DIRECT)

    def test_invalid_response_routes_latest_event_to_web(self):
        completions = QueueCompletions(["not json"])
        router = LLMQuestionRouter(
            SimpleNamespace(chat=SimpleNamespace(completions=completions))
        )

        decision = router.classify(
            "最近纸尿裤事件的最新进展如何",
            make_runtime(),
        )

        self.assertEqual(decision.route, ROUTE_WEB)

    def test_invalid_response_can_route_matching_kb_tag(self):
        completions = QueueCompletions(["not json"])
        router = LLMQuestionRouter(
            SimpleNamespace(chat=SimpleNamespace(completions=completions))
        )

        decision = router.classify("营养", make_runtime())

        self.assertEqual(decision.route, ROUTE_KNOWLEDGE)


if __name__ == "__main__":
    unittest.main()
