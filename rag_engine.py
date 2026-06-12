"""
RAG 引擎
本地关键词检索 + DeepSeek 大模型生成回答
"""
import re
import json
import time
import pathlib
import logging
from openai import OpenAI
from course_manager import Course
import config

logger = logging.getLogger(__name__)


def _extract_terms(text: str) -> list[str]:
    """简单中文分词：提取关键词"""
    cleaned = re.sub(r"[，。？！、；：\"'（）【】《》\s\n\r]", " ", text)
    terms: list[str] = []

    for m in re.finditer(r"[a-zA-Z_]\w{2,}", cleaned):
        terms.append(m.group().lower())

    for m in re.finditer(r"[一-龥]{2,6}", cleaned):
        chunk = m.group()
        terms.append(chunk)
        if len(chunk) >= 4:
            for i in range(len(chunk) - 1):
                terms.append(chunk[i:i+2])

    return list(set(terms))


def _chunk_text(text: str, size: int = 500, overlap: int = 100) -> list[str]:
    """文本分块"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end]

        if end < len(text):
            for sep in ["。", "\n\n", "？", "！", "；"]:
                pos = chunk.rfind(sep)
                if pos > size * 0.4:
                    chunk = chunk[:pos + 1]
                    break

        chunk = chunk.strip()
        if len(chunk) > 20:
            chunks.append(chunk)

        advance = max(len(chunk), size - overlap)
        start += advance

    return chunks


def _load_file(filepath: str) -> list[dict]:
    """读取单个知识文件，返回文档列表"""
    p = pathlib.Path(filepath)
    ext = p.suffix.lower()
    filename = p.name

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if ext == ".json":
        try:
            faqs = json.loads(content)
            return [
                {"content": f"问题：{faq['question']}\n答案：{faq['answer']}",
                 "source": filename}
                for faq in faqs
            ]
        except Exception as e:
            logger.warning(f"解析 JSON 文件失败 {filename}: {e}")
            return []

    chunks = _chunk_text(content)
    return [{"content": c, "source": filename} for c in chunks]


_SUPPORTED_EXTS = {".md", ".txt", ".json"}


class RAGEngine:
    """课程知识库检索 + LLM 生成"""

    def __init__(self):
        self.docs: dict[str, list[dict]] = {}
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )

    def load_knowledge(self, course: Course):
        """加载课程知识库到内存"""
        knowledge_dir = pathlib.Path(course.knowledge_path).resolve()

        if not knowledge_dir.exists():
            logger.warning(f"知识库目录不存在: {knowledge_dir}")
            return

        all_docs = []
        for f in sorted(knowledge_dir.iterdir()):
            if f.suffix.lower() in _SUPPORTED_EXTS:
                docs = _load_file(str(f))
                all_docs.extend(docs)
                logger.info(f"  已加载 {f.name}: {len(docs)} 个文档块")

        self.docs[course.id] = all_docs
        logger.info(f"课程 {course.name} 知识库已加载: {len(all_docs)} 个文档块")

    def search_local(self, course_id: str, query: str, top_k: int = 3) -> list[dict]:
        """本地知识库关键词检索"""
        documents = self.docs.get(course_id, [])
        if not documents:
            return []

        query_terms = _extract_terms(query)
        if not query_terms:
            return documents[:top_k]

        scored = []
        for doc in documents:
            score = 0
            content = doc["content"]

            for term in query_terms:
                count = content.count(term)
                if count > 0:
                    score += len(term) * count

            for line in content.split("\n"):
                if line.startswith("#"):
                    for term in query_terms:
                        if term in line:
                            score += len(term) * 3

            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def answer(self, question: str, course: Course,
               chat_history: list[dict] | None = None) -> str:
        """基于本地知识库回答问题"""
        logger.info(f"RAG 查询 [{course.name}]: {question[:80]}")

        # 1. 本地知识库检索
        local_results = self.search_local(course.id, question, top_k=3)

        # 2. 构建 prompt
        system_content = course.system_prompt

        if local_results:
            parts = []
            for i, doc in enumerate(local_results):
                parts.append(f"[参考资料 {i+1}] (来源: 本地知识 - {doc['source']})\n{doc['content'][:500]}")
            context = "\n\n---\n\n".join(parts)
            system_content += f"\n\n以下是与问题相关的参考资料，请优先基于这些资料回答：\n\n{context}"
        else:
            system_content += "\n\n暂未找到相关参考资料，请基于通用知识回答。"

        # 全局格式要求
        system_content += (
            "\n\n"
            "【重要格式要求】"
            "你是在微信群里回复消息，必须遵守以下规则："
            "1. 禁止使用 Markdown 格式（不要 **加粗**、不要 - 列表、不要 # 标题）"
            "2. 用纯文本自然语言回复，像真人微信聊天一样"
            "3. 简短直接，控制在 200 字以内，不要客套和废话"
            "4. 用中文数字（一、二、三）代替列表符号，用空行分段"
        )

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
                    temperature=0.3,
                    max_tokens=500,
                )
                answer = resp.choices[0].message.content or "抱歉，我暂时无法回答这个问题。"
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
