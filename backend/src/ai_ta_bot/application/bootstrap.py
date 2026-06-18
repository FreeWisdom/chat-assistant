"""Runtime dependency composition."""

from __future__ import annotations

from .bot_runner import BotRunner
from .question_service import QuestionService
from ..domain import HandRaiseTriggerPolicy
from ..integrations import WeChatGateway
from ..persistence import ConversationRepository
from .. import config


def build_runner(course_manager, answer_generator) -> BotRunner:
    trigger_policy = HandRaiseTriggerPolicy()
    conversations = ConversationRepository(config.BOT_STATE_DB)
    question_service = QuestionService(
        course_manager,
        answer_generator,
        conversations,
        trigger_policy,
    )
    gateway = WeChatGateway(
        allowed_chats=list(course_manager.group_map),
        db_path=config.BOT_STATE_DB,
        trigger_policy=trigger_policy,
        dry_run=config.DRY_RUN,
        allow_self=config.DEV_MODE,
        search_timeout=config.CHAT_SEARCH_TIMEOUT,
    )
    return BotRunner(
        gateway,
        question_service,
        worker_interval=config.TASK_WORKER_INTERVAL,
    )
