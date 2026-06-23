"""LLM-based routing for direct, knowledge, web, and clarification answers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re

from .. import config
from ..configuration import RuntimeBotConfig

logger = logging.getLogger(__name__)

ROUTE_DIRECT = "direct"
ROUTE_KNOWLEDGE = "knowledge"
ROUTE_WEB = "web"
ROUTE_CLARIFY = "clarify"
VALID_ROUTES = {
    ROUTE_DIRECT,
    ROUTE_KNOWLEDGE,
    ROUTE_WEB,
    ROUTE_CLARIFY,
}

_STRONG_WEB_PATTERN = re.compile(
    r"天气|气温|下雨|降雨|台风|空气质量|"
    r"新闻|事件|最新|最近|近期|进展|动态|现状|目前|"
    r"股价|股票|基金|汇率|金价|油价|币价|行情|财报|"
    r"比分|赛果|比赛结果|航班|路况|政策|法规|价格",
)
_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str = ""
    search_query: str = ""


class LLMQuestionRouter:
    """Use the configured LLM to select the cheapest sufficient answer path."""

    def __init__(self, client):
        self.client = client

    def classify(
        self,
        question: str,
        runtime: RuntimeBotConfig,
        chat_history: list[dict] | None = None,
    ) -> RouteDecision:
        knowledge_lines = []
        for kb in runtime.knowledge_bases:
            examples = "；".join(kb.route_examples[:4])
            knowledge_lines.append(
                f"- {kb.name}: {kb.description}; 标签={','.join(kb.tags)}; "
                f"示例={examples or '无'}"
            )
        recent_history = []
        for item in (chat_history or [])[-4:]:
            recent_history.append(
                f"{item.get('role', 'unknown')}: "
                f"{str(item.get('content', ''))[:160]}"
            )

        system_prompt = (
            "你是微信群问答机器人的问题路由器，只负责选择回答路径，不回答问题。\n"
            "严格按以下优先级选择成本最低且足够可靠的路径：\n"
            "1. direct：稳定的通用知识、推理、计算、写作、生活建议或闲聊，"
            "大模型自身可以回答，不需要实时事实或私有资料。"
            "“今天晚上吃什么”这类生活建议属于 direct，不要因为出现“今天”就搜索。\n"
            "2. knowledge：问题依赖当前群绑定的专业资料、内部规则、案例或知识库内容。\n"
            "3. web：只有答案依赖实时或近期外部事实时使用，例如天气、新闻事件、"
            "最新进展、价格行情、政策变化、比赛结果。不得为了普通问题滥用搜索。\n"
            "4. clarify：问题缺少关键对象、地点、时间、目标或上下文，无法可靠回答。\n"
            "只返回一个 JSON 对象，不要 Markdown："
            '{"route":"direct|knowledge|web|clarify","reason":"简短原因",'
            '"search_query":"仅 web 路径填写适合中文搜索的关键词，其他路径留空"}'
        )
        user_prompt = (
            f"群：{runtime.group}\n"
            f"机器人职责：{runtime.bot.role}\n"
            "可用知识库：\n"
            f"{chr(10).join(knowledge_lines) or '- 无'}\n"
            f"最近对话：\n{chr(10).join(recent_history) or '- 无'}\n"
            f"当前问题：{question}"
        )

        try:
            response = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=180,
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
            raw = str(response.choices[0].message.content or "").strip()
            decision = self._parse(raw)
            if decision:
                logger.info(
                    "问题路由: route=%s reason=%s search_query=%s",
                    decision.route,
                    decision.reason,
                    decision.search_query,
                )
                return decision
            logger.warning("问题路由返回格式无效，使用保守规则: %s", raw[:200])
        except Exception as exc:
            logger.warning("问题路由调用失败，使用保守规则: %s", exc)

        return self._fallback(question, runtime)

    @staticmethod
    def _parse(raw: str) -> RouteDecision | None:
        match = _JSON_PATTERN.search(raw)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        route = str(payload.get("route", "")).strip().lower()
        if route not in VALID_ROUTES:
            return None
        return RouteDecision(
            route=route,
            reason=str(payload.get("reason", "") or "").strip(),
            search_query=str(payload.get("search_query", "") or "").strip(),
        )

    @staticmethod
    def _fallback(question: str, runtime: RuntimeBotConfig) -> RouteDecision:
        text = str(question or "").strip()
        if _STRONG_WEB_PATTERN.search(text):
            return RouteDecision(
                route=ROUTE_WEB,
                reason="保守规则判断为时效性外部事实",
                search_query=text,
            )

        lowered = text.lower()
        for kb in runtime.knowledge_bases:
            candidates = [*kb.tags, *kb.route_examples]
            if any(
                str(candidate).strip()
                and str(candidate).strip().lower() in lowered
                for candidate in candidates
            ):
                return RouteDecision(
                    route=ROUTE_KNOWLEDGE,
                    reason="问题与知识库标签或示例直接匹配",
                )

        return RouteDecision(
            route=ROUTE_DIRECT,
            reason="保守规则判断可由大模型直接回答",
        )
