"""Query-time web search used when bound knowledge bases do not match."""

from __future__ import annotations

from datetime import date
import json
import logging
import re
from typing import Any

import requests

from .. import config

logger = logging.getLogger(__name__)
SEARCHABLE_TEXT_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")
# \u641c\u7d22\u67e5\u8be2\u4e2d\u9700\u8981\u8fc7\u6ee4\u7684\u7eaf\u53e3\u8bed\u8bcd\uff08\u4e0d\u542b\u5185\u5bb9\u8bcd\uff0c\u4fdd\u7559\u5bf9\u641c\u7d22\u6709\u5e2e\u52a9\u7684\u4e0a\u4e0b\u6587\u8bcd\uff09
_SEARCH_NOISE_WORDS = frozenset({
    # \u7591\u95ee/\u8bed\u6c14\u8bcd
    "\u5982\u4f55", "\u600e\u4e48", "\u600e\u4e48\u6837", "\u4ec0\u4e48\u6837", "\u4e3a\u4ec0\u4e48", "\u4e3a\u4f55",
    "\u4f55\u65f6", "\u54ea\u91cc", "\u54ea\u4e2a", "\u54ea\u4e9b", "\u662f\u8c01",
    "\u5417", "\u5462", "\u5427", "\u554a", "\u5440",
    # \u7eaf\u53e3\u8bed/\u8bf7\u6c42\uff08\u4e0d\u542b\u4efb\u4f55\u4fe1\u606f\u91cf\uff09
    "\u4e00\u4e0b", "\u80fd\u4e0d\u80fd", "\u53ef\u4e0d\u53ef\u4ee5",
    "\u6765\u8bb2", "\u6765\u8bf4", "\u544a\u8bc9\u6211", "\u4f60\u77e5\u9053", "\u5e2e\u6211", "\u6211\u60f3",
    "\u6211\u60f3\u77e5\u9053", "\u6211\u60f3\u4e86\u89e3", "\u6211\u60f3\u4e86\u89e3\u4e00\u4e0b",
    "\u67e5\u4e00\u4e0b", "\u5e2e\u6211\u67e5", "\u5e2e\u6211\u67e5\u4e00\u4e0b", "\u641c\u4e00\u4e0b",
    "\u77e5\u4e0d\u77e5\u9053", "\u4e86\u4e0d\u4e86\u89e3", "\u6e05\u695a\u5417",
    # \u52a9\u8bcd
    "\u7684",
})
IMMEDIATE_FRESHNESS_PATTERN = re.compile(
    r"今天|今日|当天|刚刚|实时|现在|目前|此刻|当下",
)
RECENT_FRESHNESS_PATTERN = re.compile(
    r"最新|最近|近期|本周|这周|新闻|动态|更新|进展|发布|上线|"
    r"政策|法规|价格|行情|版本|排名|融资|比赛|赛事",
)
NEWS_TOPIC_PATTERN = re.compile(
    r"新闻|报道|事件|比赛|赛事|政策|法规|发布|融资|动态",
)
FINANCE_TOPIC_PATTERN = re.compile(
    r"股价|股票|基金|汇率|金价|油价|币价|行情|财报|市值",
)


class TavilyWebSearcher:
    """Small Tavily Search API adapter returning normalized documents."""

    def __init__(self, api_key: str | None = None, session=None):
        self.api_key = (api_key if api_key is not None else config.TAVILY_API_KEY).strip()
        self.session = session or requests

    @staticmethod
    def _clean_query(query: str) -> str:
        """将口语化中文问题转为关键词式查询，适配 Tavily 搜索。"""
        # 去除标点
        cleaned = re.sub(
            r"[　-〿＀-￯，。！？、；：“”‘’（）【】《》\s]+",
            " ",
            str(query or ""),
        )
        # 过滤口语化/泛化词汇
        tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]
        # 按长度从长到短逐个剔除噪声词
        noise_sorted = sorted(_SEARCH_NOISE_WORDS, key=len, reverse=True)
        for word in noise_sorted:
            cleaned = cleaned.replace(word, " ")
        tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]
        return " ".join(tokens) if tokens else str(query or "").strip()

    @staticmethod
    def is_time_sensitive(query: str) -> bool:
        question = str(query or "")
        return bool(
            IMMEDIATE_FRESHNESS_PATTERN.search(question)
            or RECENT_FRESHNESS_PATTERN.search(question)
            or str(date.today().year) in question
        )

    @staticmethod
    def _time_range(query: str) -> str:
        question = str(query or "")
        if IMMEDIATE_FRESHNESS_PATTERN.search(question):
            return "day"
        if TavilyWebSearcher.is_time_sensitive(question):
            return config.WEB_SEARCH_FRESH_TIME_RANGE
        return config.WEB_SEARCH_TIME_RANGE

    @staticmethod
    def _topic(query: str) -> str:
        question = str(query or "")
        if FINANCE_TOPIC_PATTERN.search(question):
            return "finance"
        if NEWS_TOPIC_PATTERN.search(question):
            return "news"
        return "general"

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, Any]]:
        question = str(query or "").strip()[:400]
        if not question or not SEARCHABLE_TEXT_PATTERN.search(question):
            logger.warning("跳过无有效文字的联网搜索请求")
            return []
        if not self.api_key:
            logger.warning("联网搜索已启用，但 TAVILY_API_KEY 未配置")
            return []

        limit = max(1, min(max_results or config.WEB_SEARCH_MAX_RESULTS, 20))
        primary_time_range = self._time_range(question)
        topic = self._topic(question)
        results = self._search_once(
            question,
            limit=limit,
            topic=topic,
            time_range=primary_time_range,
        )
        if results is None:
            return []
        fallback_time_range = config.WEB_SEARCH_FALLBACK_TIME_RANGE
        if (
            not results
            and not self.is_time_sensitive(question)
            and fallback_time_range
            and fallback_time_range != primary_time_range
        ):
            logger.info(
                "近期搜索无结果，放宽时间范围: %s -> %s",
                primary_time_range,
                fallback_time_range,
            )
            results = self._search_once(
                question,
                limit=limit,
                topic=topic,
                time_range=fallback_time_range,
            )
        return results or []

    def _search_once(
        self,
        question: str,
        *,
        limit: int,
        topic: str,
        time_range: str,
    ) -> list[dict[str, Any]] | None:
        keywords = self._clean_query(question)
        search_query = keywords
        if self.is_time_sensitive(question):
            search_query = f"{keywords} {date.today().isoformat()}"
        payload: dict[str, Any] = {
            "query": search_query,
            "search_depth": config.WEB_SEARCH_DEPTH,
            "max_results": limit,
            "topic": topic,
            "include_answer": False,
            "include_raw_content": False,
        }
        if time_range:
            payload["time_range"] = time_range
        if topic == "general" and config.WEB_SEARCH_COUNTRY:
            payload["country"] = config.WEB_SEARCH_COUNTRY

        try:
            response = self.session.post(
                config.TAVILY_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.WEB_SEARCH_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as exc:
            response = exc.response
            status = response.status_code if response is not None else "unknown"
            detail = ""
            if response is not None:
                try:
                    payload = response.json()
                    detail = str(
                        payload.get("detail")
                        or payload.get("message")
                        or payload.get("error")
                        or ""
                    )
                except Exception:
                    detail = str(response.text or "")
            logger.warning(
                "联网搜索请求失败: status=%s detail=%s",
                status,
                detail[:300] or "<empty>",
            )
            return None
        except Exception as exc:
            logger.warning("联网搜索失败: %s", exc)
            return None

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for item in data.get("results", []):
            title = str(item.get("title", "") or "").strip()
            url = str(item.get("url", "") or "").strip()
            content = str(item.get("content", "") or "").strip()
            if not url or url in seen_urls or not (title or content):
                continue
            seen_urls.add(url)
            results.append({
                "chunk_id": f"web-search-{len(results) + 1}",
                "content": content[:1500] or title,
                "source": title or url,
                "title": title,
                "url": url,
                "provider": "web_search",
                "kb_id": "__web_search__",
                "kb_name": "联网搜索",
                "kb_tags": [],
                "priority": 0,
                "_score": float(item.get("score", 0) or 0),
                "_search_topic": topic,
                "_search_time_range": time_range,
                "_searched_at": date.today().isoformat(),
            })

        logger.info(
            "联网搜索完成: query=%s topic=%s time_range=%s results=%s",
            search_query[:80],
            topic,
            time_range,
            len(results),
        )
        return results


class VolcengineWebSearcher:
    """火山引擎联网搜索 API 适配器。

    基于官方 byted-web-search skill 实现:
    - API Key 模式: https://open.feedcoopapi.com/search_api/web_search
    - 核心能力: queryRewrite 自动改写口语化查询、authLevel 过滤权威来源
    - 中文搜索质量显著优于 Tavily
    """

    _TIME_RANGE_MAP = {
        "day": "OneDay",
        "week": "OneWeek",
        "month": "OneMonth",
        "year": "OneYear",
    }
    _API_URL = "https://open.feedcoopapi.com/search_api/web_search"
    _TRAFFIC_TAG = "ai_ta_bot_search"

    def __init__(self, api_key: str | None = None, session=None):
        self.api_key = (api_key if api_key is not None else config.VOLCENGINE_API_KEY).strip()
        self.session = session or requests

    @staticmethod
    def is_time_sensitive(query: str) -> bool:
        question = str(query or "")
        return bool(
            IMMEDIATE_FRESHNESS_PATTERN.search(question)
            or RECENT_FRESHNESS_PATTERN.search(question)
            or str(date.today().year) in question
        )

    @staticmethod
    def _time_range(query: str) -> str:
        question = str(query or "")
        if IMMEDIATE_FRESHNESS_PATTERN.search(question):
            return "day"
        if VolcengineWebSearcher.is_time_sensitive(question):
            return "week"
        return "month"

    @staticmethod
    def _auth_level(query: str) -> int:
        question = str(query or "")
        if NEWS_TOPIC_PATTERN.search(question) or FINANCE_TOPIC_PATTERN.search(question):
            return 1
        return 0

    @staticmethod
    def _clean_query(query: str) -> str:
        """轻量清洗 — 火山引擎自带 queryRewrite，客户端只需去标点和口语噪声。"""
        text = str(query or "").strip()
        for ch in "，。！？、；：""''（）【】《》":
            text = text.replace(ch, " ")
        noise_sorted = sorted(_SEARCH_NOISE_WORDS, key=len, reverse=True)
        for word in noise_sorted:
            text = text.replace(word, " ")
        keywords = [t for t in text.split() if len(t) >= 2]
        return " ".join(keywords) if keywords else str(query or "").strip()

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, Any]]:
        question = str(query or "").strip()[:400]
        if not question or not SEARCHABLE_TEXT_PATTERN.search(question):
            logger.warning("跳过无有效文字的联网搜索请求")
            return []
        if not self.api_key:
            logger.warning("联网搜索已启用，但 VOLCENGINE_API_KEY 未配置")
            return []

        limit = max(1, min(max_results or config.WEB_SEARCH_MAX_RESULTS, 50))
        time_range = self._time_range(question)
        volc_time_range = self._TIME_RANGE_MAP.get(time_range, "OneWeek")
        auth_level = self._auth_level(question)
        raw_query = self._clean_query(question)

        # 官方请求体格式 (PascalCase)
        body: dict[str, Any] = {
            "Query": raw_query,
            "SearchType": "web",
            "Count": limit,
            "NeedSummary": True,
            "QueryControl": {"QueryRewrite": True},
            "TimeRange": volc_time_range,
        }
        if auth_level > 0:
            body["Filter"] = {"AuthInfoLevel": auth_level}

        try:
            response = self.session.post(
                self._API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Traffic-Tag": self._TRAFFIC_TAG,
                },
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=config.WEB_SEARCH_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as exc:
            resp = exc.response
            status = resp.status_code if resp is not None else "unknown"
            detail = ""
            if resp is not None:
                try:
                    detail = str(resp.json().get("ResponseMetadata", {}).get("Error", {}).get("Message", "") or "")
                except Exception:
                    detail = str(resp.text or "")[:300]
            logger.warning(
                "火山引擎搜索请求失败: status=%s detail=%s",
                status,
                detail or "<empty>",
            )
            return []
        except Exception as exc:
            logger.warning("火山引擎搜索失败: %s", exc)
            return []

        # 解析官方响应格式: Result.WebResults[].{Title, Url, Summary}
        web_results = data.get("Result", {}).get("WebResults") or []
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for item in web_results:
            title = str(item.get("Title", "") or "").strip()
            url = str(item.get("Url", "") or "").strip()
            summary = str(item.get("Summary", "") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "chunk_id": f"volc-{len(results) + 1}",
                "content": summary[:1500] or title,
                "source": title or url,
                "title": title,
                "url": url,
                "provider": "volcengine_search",
                "kb_id": "__web_search__",
                "kb_name": "联网搜索",
                "kb_tags": [],
                "priority": 0,
                "_score": float(item.get("SortId", 0) or 0),
                "_search_time_range": volc_time_range,
                "_searched_at": date.today().isoformat(),
            })

        logger.info(
            "火山引擎搜索完成: query=%s time_range=%s auth=%s results=%s",
            raw_query[:60],
            volc_time_range,
            auth_level,
            len(results),
        )
        return results
