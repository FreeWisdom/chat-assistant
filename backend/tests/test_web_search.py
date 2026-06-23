import unittest
from unittest.mock import patch

import requests
from ai_ta_bot.knowledge.web_search import TavilyWebSearcher


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {
                    "title": "测试来源",
                    "url": "https://example.com/result",
                    "content": "这是和问题最相关的网页摘要。",
                    "score": 0.9,
                }
            ]
        }


class FakeSession:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [FakeResponse()])

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class FakeEmptyResponse(FakeResponse):
    def json(self):
        return {"results": []}


class FakeErrorResponse:
    status_code = 400
    text = '{"detail":"invalid query"}'

    def raise_for_status(self):
        raise requests.HTTPError(response=self)

    def json(self):
        return {"detail": "invalid query"}


class FakeErrorSession:
    def post(self, url, **kwargs):
        return FakeErrorResponse()


class TavilyWebSearcherTests(unittest.TestCase):
    def test_normalizes_search_results_and_uses_bearer_auth(self):
        session = FakeSession()
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        results = searcher.search("如何搭配高蛋白早餐", max_results=3)

        self.assertEqual(results[0]["provider"], "web_search")
        self.assertEqual(results[0]["url"], "https://example.com/result")
        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["max_results"], 3)
        self.assertEqual(kwargs["json"]["time_range"], "month")
        self.assertEqual(kwargs["json"]["topic"], "general")
        self.assertEqual(kwargs["json"]["country"], "china")

    def test_missing_api_key_returns_no_results(self):
        self.assertEqual(TavilyWebSearcher(api_key="").search("测试"), [])

    def test_skips_query_without_searchable_text(self):
        session = FakeSession()
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        self.assertEqual(searcher.search("???? 。。。"), [])
        self.assertEqual(session.calls, [])

    def test_http_error_returns_no_results_without_raising(self):
        searcher = TavilyWebSearcher(
            api_key="secret",
            session=FakeErrorSession(),
        )
        with patch("ai_ta_bot.knowledge.web_search.logger.warning") as warning:
            self.assertEqual(searcher.search("有效问题"), [])

        warning.assert_called_once()
        self.assertIn("status=%s", warning.call_args.args[0])

    def test_latest_query_uses_recent_window_even_if_it_is_general(self):
        session = FakeSession()
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        searcher.search("DeepSeek 最新版本是什么", max_results=3)

        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"]["time_range"], "week")
        self.assertEqual(kwargs["json"]["topic"], "general")
        self.assertIn(str(__import__("datetime").date.today().year), kwargs["json"]["query"])

    def test_today_query_uses_day_and_news_omits_country(self):
        session = FakeSession()
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        searcher.search("今天有哪些 AI 新闻", max_results=3)

        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"]["time_range"], "day")
        self.assertEqual(kwargs["json"]["topic"], "news")
        self.assertNotIn("country", kwargs["json"])

    def test_current_market_query_uses_finance_and_day(self):
        session = FakeSession()
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        searcher.search("目前金价是多少", max_results=3)

        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["json"]["time_range"], "day")
        self.assertEqual(kwargs["json"]["topic"], "finance")
        self.assertNotIn("country", kwargs["json"])

    def test_empty_regular_search_falls_back_to_one_year(self):
        session = FakeSession([FakeEmptyResponse(), FakeResponse()])
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        results = searcher.search("如何搭配早餐", max_results=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["json"]["time_range"], "month")
        self.assertEqual(session.calls[1][1]["json"]["time_range"], "year")

    def test_empty_latest_search_does_not_fall_back_to_old_results(self):
        session = FakeSession([FakeEmptyResponse()])
        searcher = TavilyWebSearcher(api_key="secret", session=session)

        results = searcher.search("最新行业进展", max_results=3)

        self.assertEqual(results, [])
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][1]["json"]["time_range"], "week")


if __name__ == "__main__":
    unittest.main()
