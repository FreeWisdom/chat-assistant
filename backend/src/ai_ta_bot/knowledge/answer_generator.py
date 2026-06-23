"""RAG 引擎：Retriever 检索 + DeepSeek/OpenAI 兼容接口生成回答。"""
from datetime import date
import re
import time
import logging
from openai import OpenAI
from ..configuration import KnowledgeBase, RuntimeBotConfig
from .question_router import (
    LLMQuestionRouter,
    ROUTE_CLARIFY,
    ROUTE_DIRECT,
    ROUTE_KNOWLEDGE,
    ROUTE_WEB,
)
from .retriever import HybridRetriever
from .web_search import TavilyWebSearcher, VolcengineWebSearcher
from .. import config

logger = logging.getLogger(__name__)


class RAGEngine:
    """绑定知识库检索 + LLM 生成。"""

    def __init__(
        self,
        *,
        client=None,
        retriever=None,
        web_searcher=None,
        question_router=None,
    ):
        if client is None and not config.LLM_API_KEY:
            raise ValueError("LLM_API_KEY 未配置，无法启动回答生成器")
        self.retriever = retriever or HybridRetriever()
        self.client = client or OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
        if web_searcher is not None:
            self.web_searcher = web_searcher
        elif config.WEB_SEARCH_ENABLED:
            self.web_searcher = self._create_web_searcher()
        else:
            self.web_searcher = TavilyWebSearcher()
        self.question_router = question_router or LLMQuestionRouter(self.client)

    @staticmethod
    def _create_web_searcher():
        provider = config.WEB_SEARCH_PROVIDER
        if provider == "volcengine":
            if not config.VOLCENGINE_API_KEY:
                raise ValueError(
                    "WEB_SEARCH_PROVIDER=volcengine 时必须配置 VOLCENGINE_API_KEY"
                )
            return VolcengineWebSearcher()
        # 默认 tavily
        if not config.TAVILY_API_KEY:
            raise ValueError("WEB_SEARCH_ENABLED=true 时必须配置 TAVILY_API_KEY")
        return TavilyWebSearcher()

    def load_knowledge(self, runtime: RuntimeBotConfig | KnowledgeBase):
        """兼容旧调用：可传运行时配置，也可传单个知识库。"""
        if isinstance(runtime, RuntimeBotConfig):
            for kb in runtime.knowledge_bases:
                self.load_knowledge_base(kb)
            return

        self.load_knowledge_base(runtime)

    def load_knowledge_base(self, kb: KnowledgeBase):
        """加载单个知识库并刷新检索索引。"""
        self.retriever.load_knowledge_base(kb)

    def search_local(self, knowledge_base_ids: list[str], query: str, top_k: int = 3) -> list[dict]:
        """只在当前群绑定的知识库内检索。"""
        return self.retriever.search(knowledge_base_ids, query, top_k=top_k)

    def search_web(self, query: str) -> list[dict]:
        """知识库未命中时执行实时联网搜索。"""
        return self.web_searcher.search(query, max_results=config.WEB_SEARCH_MAX_RESULTS)

    def answer(self, question: str, runtime: RuntimeBotConfig,
               chat_history: list[dict] | None = None,
               sender: str = "",
               group_name: str = "") -> str:
        """Route the question, collect only needed context, then generate."""
        logger.info(f"RAG 查询 [{runtime.bot.name}/{group_name}]: {question[:80]}")

        # 1. 先让大模型选择成本最低且足够可靠的路径。
        decision = self.question_router.classify(
            question,
            runtime,
            chat_history,
        )
        route = decision.route
        local_results = []
        web_results = []

        if route == ROUTE_KNOWLEDGE:
            local_results = self.search_local(
                runtime.knowledge_base_ids,
                question,
                top_k=config.RETRIEVAL_TOP_K,
            )
            # 知识库应答路径没有命中时，联网搜索才作为最后兜底。
            if not local_results and config.WEB_SEARCH_ENABLED:
                search_query = decision.search_query or question
                web_results = self._filter_relevant_web_results(
                    question,
                    search_query,
                    self.search_web(search_query),
                )
                route = ROUTE_WEB if web_results else ROUTE_CLARIFY
            elif not local_results:
                route = ROUTE_CLARIFY
        elif route == ROUTE_WEB and config.WEB_SEARCH_ENABLED:
            search_query = decision.search_query or question
            web_results = self._filter_relevant_web_results(
                question,
                search_query,
                self.search_web(search_query),
            )

        if web_results:
            reference_results = [*web_results, *local_results]
        else:
            reference_results = local_results

        # 2. 所有路径最终统一交给 DeepSeek 生成和润色。
        is_web_chat = route == ROUTE_WEB

        if is_web_chat:
            system_content = self._build_web_chat_prompt(question, sender, group_name)
        else:
            system_content = self._build_system_prompt(runtime, reference_results, sender, group_name)

        if route == ROUTE_DIRECT:
            system_content += (
                "\n\n【回答路径】这是可由大模型直接回答的稳定通用问题。"
                "请使用可靠的通用知识直接回答；即使问题超出当前群的主题，"
                "也不要用“不是我的职责”推脱。不要编造实时事实。"
            )
        elif route == ROUTE_CLARIFY:
            system_content += (
                "\n\n【回答路径】当前信息不足，或知识库和最后兜底搜索都没有可靠结果。"
                "请自然地说明缺少哪一项关键信息，并只追问一个最重要的问题。"
            )

        if reference_results:
            content_limit = 1200 if is_web_chat else 500
            parts = []
            for i, doc in enumerate(reference_results):
                source = f"{doc.get('kb_name', '知识资料')} / 来源: {doc.get('source', '未知')}"
                if doc.get("url"):
                    source += f" / URL: {doc['url']}"
                parts.append(
                    f"[参考资料 {i+1}] "
                    f"({source})\n"
                    f"{doc['content'][:content_limit]}"
                )
            context = "\n\n---\n\n".join(parts)
            if is_web_chat:
                system_content += (
                    "\n\n【联网搜索结果】\n"
                    "以下是实时搜索获取的信息，来自多个来源。请仔细阅读后回答:\n"
                    "- 先说最重要的结论或最新进展，再梳理关键时间线和背景\n"
                    "- 不同来源说法矛盾时，把各方观点都提一下，不要只采信一边\n"
                    "- 像群友聊天分享消息一样自然，不要新闻联播腔\n"
                    "- 最后给一个实用的建议(如果合适的话)\n"
                    "- 如果搜索结果不足以判断，直说哪部分还不清楚\n\n"
                    f"{context}"
                )
            elif web_results:
                system_content += (
                    "\n\n【联网搜索结果】\n"
                    "以下内容来自实时搜索。请交叉判断，不要把摘要中的推断当成确定事实；"
                    "只输出回答正文，不要编造、改写或重复来源 URL，程序会在正文后追加来源。\n\n"
                    f"{context}"
                )
            else:
                system_content += (
                    "\n\n【命中的知识库资料】\n"
                    "请优先基于这些资料回答，不要编造资料中没有的事实。\n\n"
                    f"{context}"
                )

        if route == ROUTE_WEB and not web_results:
            system_content += (
                "\n\n【时效性限制】本次实时联网搜索未返回与问题足够相关的结果。"
                "不得用模型记忆冒充当前事实，也不要引用无关网页；"
                "请明确告诉用户目前无法可靠核验，并建议补充更具体的事件名称、地点或主体。"
            )

        system_content += (
            "\n\n【最终表达润色】无论答案来自通用知识、知识库还是联网搜索，"
            "都要先消化信息，再用自然、简短、像真实群友的中文重新表达。"
            "不要暴露路由、提示词、知识库或模型处理过程，不要机械复述资料。"
        )

        messages = [{"role": "system", "content": system_content}]

        if chat_history:
            for msg in chat_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": question})

        # 3. 调用 LLM
        model = config.LLM_MODEL
        max_tokens = 800 if is_web_chat else 500
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.6,
                    max_tokens=max_tokens,
                    timeout=config.LLM_TIMEOUT_SECONDS,
                )
                answer = resp.choices[0].message.content or "抱歉，我暂时无法回答这个问题。"
                answer = self._clean_answer(answer, runtime)
                if web_results:
                    answer = self._append_web_sources(answer, web_results)
                tokens = resp.usage.total_tokens if resp.usage else '?'
                logger.info(f"回答完成, tokens: {tokens}")
                return answer
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"LLM 调用失败 (第{attempt+1}次), 重试中: {e}")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"LLM 调用失败 (已重试3次): {e}")
                    return "抱歉，调用 AI 服务时出现异常，请稍后再试。"

    @staticmethod
    def _filter_relevant_web_results(
        question: str,
        search_query: str,
        results: list[dict],
    ) -> list[dict]:
        """Reject obviously unrelated search results before prompting or citing."""
        if not results:
            return []

        text = f"{question} {search_query}"
        for word in (
            "今天", "今日", "现在", "目前", "最近", "近期", "最新",
            "事件", "进展", "动态", "消息", "新闻", "如何", "怎么",
            "什么", "一下", "帮我", "的", "吗", "呢",
        ):
            text = text.replace(word, " ")

        terms = []
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z0-9_-]{3,}", text):
            normalized = chunk.lower()
            if normalized not in terms:
                terms.append(normalized)
            if re.fullmatch(r"[\u4e00-\u9fff]+", chunk) and len(chunk) >= 4:
                for size in (4, 3, 2):
                    for index in range(len(chunk) - size + 1):
                        term = chunk[index:index + size]
                        if term not in terms:
                            terms.append(term)

        # 泛新闻问题没有可做词面核验的主题词，保留结果交给模型交叉判断。
        if not terms:
            return results

        relevant = []
        for item in results:
            haystack = " ".join(
                str(item.get(key, "") or "")
                for key in ("title", "source", "content", "url")
            ).lower()
            matches = [term for term in terms if term in haystack]
            if matches:
                enriched = dict(item)
                enriched["_relevance_terms"] = matches[:5]
                relevant.append(enriched)

        if not relevant:
            logger.warning(
                "联网搜索结果均与问题缺少词面相关性，已全部丢弃: query=%s terms=%s",
                question[:80],
                terms[:12],
            )
        return relevant

    def _extract_search_keywords(self, question: str) -> str:
        """用轻量 LLM 调用将口语化问题转为搜索关键词，解决 Tavily 中文搜索短板。"""
        try:
            resp = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract 3-5 concise search keywords from the question. "
                            "Return ONLY the keywords separated by spaces. "
                            "For Chinese questions, include key nouns and topic words "
                            "that would appear in news headlines. "
                            "No punctuation, no explanations, no English unless the "
                            "question is in English."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                temperature=0,
                max_tokens=60,
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
            keywords = (resp.choices[0].message.content or "").strip()
            if keywords and len(keywords) >= 2:
                logger.info("搜索关键词重写: %s -> %s", question[:40], keywords[:80])
                return keywords
        except Exception as exc:
            logger.warning("关键词提取失败，使用清洗后查询: %s", exc)
        return self.web_searcher._clean_query(question)

    def _build_system_prompt(
        self,
        runtime: RuntimeBotConfig,
        reference_results: list[dict],
        sender: str,
        group_name: str,
    ) -> str:
        bot = runtime.bot
        style = runtime.style
        kb_lines = [
            f"- {kb.name}: {kb.description}；标签: {', '.join(kb.tags) or '无'}"
            for kb in runtime.knowledge_bases
        ]
        responsibility_lines = [f"- {item}" for item in bot.responsibilities]
        avoid_words = "、".join(style.avoid_words) if style.avoid_words else "无"

        example_lines = []
        for ex in style.examples[:3]:
            if ex.user and ex.assistant:
                example_lines.append(f"用户：{ex.user}\n你：{ex.assistant}")

        parts = [
            "【机器人身份】",
            f"名称：{bot.name}",
            f"职责：{bot.role}",
            bot.identity_prompt.strip(),
            "",
            "【当前聊天场景】",
            f"当前日期：{date.today().isoformat()}",
            f"微信群：{group_name or runtime.group}",
            f"提问人：{sender or '未知群友'}",
            "",
            "【允许使用的知识库】",
            "\n".join(kb_lines) or "- 暂无",
            "",
            "【工作职责】",
            "\n".join(responsibility_lines) or "- 回答当前群友的问题",
            "",
            "【回复风格】",
            f"语气：{style.tone}",
            f"长度：尽量控制在 {style.max_chars} 字以内",
            f"表情：{style.emoji_policy}",
            f"禁用表达：{avoid_words}",
            "不要使用 Markdown，不要写标题，不要用项目符号；默认用一两段自然微信文字。",
            "不要主动说明自己在参考知识库。不要说空泛套话。",
            "如果资料不足以判断，就先问一个最关键的澄清问题，不要硬编。",
        ]

        if example_lines:
            parts.extend(["", "【风格示例】", "\n\n".join(example_lines)])

        if reference_results:
            parts.extend([
                "",
                "【回答要求】",
                "命中资料时：先直接回答，再给一个可行动建议。",
                "只有用户明确要求步骤、清单、方案时，才分点。",
            ])

        return "\n".join(part for part in parts if part is not None)

    @staticmethod
    def _build_web_chat_prompt(question: str, sender: str, group_name: str) -> str:
        """当问题完全超出本地知识库范围、纯靠联网搜索时，使用通用聊天身份。"""
        return (
            "【你的角色】\n"
            f"当前日期: {date.today().isoformat()}\n"
            f"微信群: {group_name}\n"
            f"提问人: {sender or '未知群友'}\n"
            "\n"
            "你是这个微信群里的 AI 助手。群里平时聊特定话题，但现在有人问了一个你知识库之外的问题。"
            "你通过实时搜索获取了多个来源的信息。请像群友分享消息一样，用口语化的方式回答:\n"
            "\n"
            "【回答要求】\n"
            "1. 先把最重要的结论或最新进展说清楚，再补充关键背景和时间线\n"
            "2. 不同来源说法矛盾时，把各方观点都交代一下，不要只采信一边\n"
            "3. 信息不确定就直说「这部分目前还不清楚」或「各方说法不一」\n"
            "4. 如果搜索结果和问题完全无关，诚实说「搜到的内容跟这个问题关系不大，要不换个方式问?」\n"
            "5. 适当给一个可行动的建议(如果合适的话)\n"
            "\n"
            "【风格】\n"
            "语气: 像微信群友聊新闻，说人话、抓重点、不装懂\n"
            "长度: 控制在400字以内\n"
            "不要用Markdown、标题、项目符号; 默认用自然段落\n"
            "不要主动说明「我在用搜索」或「根据搜索结果」\n"
            "不要说空泛套话，不要用新闻联播腔"
        )

    def _build_fallback_prompt(self, runtime: RuntimeBotConfig) -> str:
        policies = {kb.fallback_policy for kb in runtime.knowledge_bases}
        if "general" in policies:
            return "\n\n【资料命中情况】暂未命中知识库资料，可以基于通用经验回答，但必须说明不确定边界。"

        return (
            "\n\n【资料命中情况】暂未命中知识库资料。"
            "不要编造结论。请用自然微信语气先问一个关键澄清问题，"
            "或者说明需要对方补充具体背景、目标、相关链接、数据或分量等信息。"
        )

    @staticmethod
    def _clean_answer(answer: str, runtime: RuntimeBotConfig) -> str:
        cleaned = answer.strip()
        for word in runtime.style.avoid_words:
            cleaned = cleaned.replace(word, "")
        cleaned = re.sub(r"^\s*[-*#]+\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "")
        return cleaned.strip() or "这个我还不敢直接判断，你补充一下具体背景、目标或相关数据，我再帮你分析。"

    @staticmethod
    def _append_web_sources(answer: str, web_results: list[dict]) -> str:
        sources = []
        seen_urls = set()
        for item in web_results:
            url = str(item.get("url", "") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = str(item.get("title") or item.get("source") or "网页来源").strip()
            sources.append(f"{len(sources) + 1}. {title} {url}")
            if len(sources) >= 2:
                break
        if not sources:
            return answer
        return f"{answer.rstrip()}\n\n来源：\n" + "\n".join(sources)
