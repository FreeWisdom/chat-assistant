"""Runtime dependency composition."""

from __future__ import annotations

from .bot_runner import BotRunner
from .question_service import QuestionService
from ..domain import HandRaiseTriggerPolicy
from ..integrations import WeChatGateway
from ..persistence import ConversationRepository, TaskMetadataRepository
from .. import config


def build_runner(course_manager, answer_generator) -> BotRunner:
    trigger_policy = HandRaiseTriggerPolicy()
    conversations = ConversationRepository(config.BOT_STATE_DB)
    task_metadata = TaskMetadataRepository(config.BOT_STATE_DB)
    question_service = QuestionService(
        course_manager,
        answer_generator,
        conversations,
        trigger_policy,
        task_metadata,
    )
    gateway = WeChatGateway(
        allowed_chats=list(course_manager.group_map),
        db_path=config.BOT_STATE_DB,
        trigger_policy=trigger_policy,
        dry_run=config.DRY_RUN,
        allow_self=config.DEV_MODE,
        bot_names=config.BOT_MENTION_NAMES,
        search_timeout=config.CHAT_SEARCH_TIMEOUT,
        task_metadata=task_metadata,
        max_attempts=config.TASK_MAX_ATTEMPTS,
        retry_base_seconds=config.TASK_RETRY_BASE_SECONDS,
        retry_max_seconds=config.TASK_RETRY_MAX_SECONDS,
        send_verify_timeout=config.SEND_VERIFY_TIMEOUT,
        send_verify_interval=config.SEND_VERIFY_INTERVAL,
    )
    return BotRunner(
        gateway,
        question_service,
        worker_interval=config.TASK_WORKER_INTERVAL,
        group_worker_count=config.GROUP_WORKER_COUNT,
        health_path=config.BOT_HEALTH_PATH,
    )
