"""Use case for turning one persisted WeChat task into an answer."""

from __future__ import annotations

from dataclasses import dataclass

from configuration import CourseManager
from domain import HandRaiseTriggerPolicy
from persistence import ConversationRepository


@dataclass(frozen=True)
class PreparedAnswer:
    task_id: int
    group_name: str
    sender: str
    sender_key: str
    question: str
    answer: str


class QuestionService:
    """Coordinate trigger parsing, user memory, retrieval, and generation."""

    def __init__(
        self,
        course_manager: CourseManager,
        answer_generator,
        conversation_repository: ConversationRepository,
        trigger_policy: HandRaiseTriggerPolicy,
    ):
        self.course_manager = course_manager
        self.answer_generator = answer_generator
        self.conversations = conversation_repository
        self.trigger_policy = trigger_policy

    def prepare(self, task) -> PreparedAnswer:
        runtime = self.course_manager.get_course(task.chat_name)
        if runtime is None:
            raise ValueError(f"微信群没有运行时配置: {task.chat_name}")

        question = self.trigger_policy.extract(task.content)
        if not question:
            raise ValueError("消息不符合严格 #举手 触发规则")

        sender = str(task.sender or "unknown").strip() or "unknown"
        sender_key = self._sender_key(task, sender)
        history = self.conversations.recent(task.chat_name, sender_key, limit=6)
        answer = self.answer_generator.answer(
            question,
            runtime,
            history,
            sender=sender,
            group_name=task.chat_name,
        )
        return PreparedAnswer(
            task_id=task.id,
            group_name=task.chat_name,
            sender=sender,
            sender_key=sender_key,
            question=question,
            answer=answer,
        )

    def record_success(self, prepared: PreparedAnswer) -> None:
        self.conversations.append(
            prepared.group_name,
            prepared.sender_key,
            "user",
            prepared.question,
        )
        self.conversations.append(
            prepared.group_name,
            prepared.sender_key,
            "assistant",
            prepared.answer,
        )
        self.conversations.trim(
            prepared.group_name,
            prepared.sender_key,
            keep=20,
        )

    @staticmethod
    def _sender_key(task, sender: str) -> str:
        if sender not in {"", "unknown", "friend", task.chat_name}:
            return sender
        message_identity = (
            getattr(task, "message_id", None)
            or getattr(task, "message_hash", None)
            or "unresolved"
        )
        return f"unresolved:{message_identity}"
