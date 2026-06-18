"""RAG 引擎：Retriever 检索 + DeepSeek/OpenAI 兼容接口生成回答。"""
import re
import time
import logging
from openai import OpenAI
from configuration import KnowledgeBase, RuntimeBotConfig
from .retriever import HybridRetriever
import config

logger = logging.getLogger(__name__)


class RAGEngine:
    """绑定知识库检索 + LLM 生成。"""

    def __init__(self):
        if not config.LLM_API_KEY:
            raise ValueError("LLM_API_KEY 未配置，无法启动回答生成器")
        self.retriever = HybridRetriever()
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )

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

    def answer(self, question: str, runtime: RuntimeBotConfig,
               chat_history: list[dict] | None = None,
               sender: str = "",
               group_name: str = "") -> str:
        """基于绑定知识库回答问题。"""
        logger.info(f"RAG 查询 [{runtime.bot.name}/{group_name}]: {question[:80]}")

        # 1. 知识库检索：关键词 + 可用时的 Chroma 向量检索。
        local_results = self.search_local(runtime.knowledge_base_ids, question, top_k=config.RETRIEVAL_TOP_K)

        # 2. 构建 prompt
        system_content = self._build_system_prompt(runtime, local_results, sender, group_name)

        if local_results:
            parts = []
            for i, doc in enumerate(local_results):
                source = f"{doc['kb_name']} / 来源: {doc['source']}"
                if doc.get("url"):
                    source += f" / URL: {doc['url']}"
                parts.append(
                    f"[参考资料 {i+1}] "
                    f"({source})\n"
                    f"{doc['content'][:500]}"
                )
            context = "\n\n---\n\n".join(parts)
            system_content += f"\n\n【命中的知识库资料】\n请优先基于这些资料回答，不要编造资料中没有的事实。\n\n{context}"
        else:
            system_content += self._build_fallback_prompt(runtime)

        messages = [{"role": "system", "content": system_content}]

        if chat_history:
            for msg in chat_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": question})

        # 3. 调用 LLM
        model = config.LLM_MODEL
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.6,
                    max_tokens=500,
                    timeout=config.LLM_TIMEOUT_SECONDS,
                )
                answer = resp.choices[0].message.content or "抱歉，我暂时无法回答这个问题。"
                answer = self._clean_answer(answer, runtime)
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

    def _build_system_prompt(
        self,
        runtime: RuntimeBotConfig,
        local_results: list[dict],
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

        if local_results:
            parts.extend([
                "",
                "【回答要求】",
                "命中资料时：先直接回答，再给一个可行动建议。",
                "只有用户明确要求步骤、清单、方案时，才分点。",
            ])

        return "\n".join(part for part in parts if part is not None)

    def _build_fallback_prompt(self, runtime: RuntimeBotConfig) -> str:
        policies = {kb.fallback_policy for kb in runtime.knowledge_bases}
        if "general" in policies:
            return "\n\n【资料命中情况】暂未命中知识库资料，可以基于通用经验回答，但必须说明不确定边界。"

        return (
            "\n\n【资料命中情况】暂未命中知识库资料。"
            "不要编造结论。请用自然微信语气先问一个关键澄清问题，"
            "或者说明需要对方补充项目玩法、链接、目标人群、投入预算等信息。"
        )

    def _clean_answer(self, answer: str, runtime: RuntimeBotConfig) -> str:
        cleaned = answer.strip()
        for word in runtime.style.avoid_words:
            cleaned = cleaned.replace(word, "")
        cleaned = re.sub(r"^\s*[-*#]+\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "")
        return cleaned.strip() or "这个我还不敢直接判断，你把具体玩法或链接发我，我再帮你拆。"
