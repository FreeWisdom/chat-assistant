"""Load YAML configuration into runtime models."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .. import config
from .models import (
    BotProfile,
    BotStyle,
    GroupBinding,
    KnowledgeBase,
    RuntimeBotConfig,
    StyleExample,
)

logger = logging.getLogger(__name__)


class CourseManager:
    """Keep the legacy class name while exposing a single runtime config loader."""

    def __init__(self):
        self.bot_profiles: dict[str, BotProfile] = {}
        self.styles: dict[str, BotStyle] = {}
        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        self.bindings: list[GroupBinding] = []
        self.group_map: dict[str, RuntimeBotConfig] = {}
        self.exclude_groups: list[str] = []
        self.admins: list[str] = []
        self.cooldown_seconds: int = 30
        self.smart_detection: bool = False

    @property
    def courses(self) -> list[RuntimeBotConfig]:
        return list(self.group_map.values())

    def load(self, config_path: str | Path):
        with Path(config_path).open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        if "botProfiles" not in data:
            raise ValueError("配置格式过旧，请使用 botProfiles/styles/knowledgeBases/bindings")
        self._load_v2(data)

    def _load_v2(self, data: dict) -> None:
        self.bot_profiles = {
            item["id"]: BotProfile(
                id=item["id"],
                name=item["name"],
                role=item.get("role", ""),
                style_id=item["styleId"],
                answer_policy_id=item.get("answerPolicyId", "strict-kb"),
                responsibilities=item.get("responsibilities", []),
                identity_prompt=item.get("identityPrompt", ""),
            )
            for item in data.get("botProfiles", [])
        }

        self.styles = {}
        for item in data.get("styles", []):
            examples = [
                StyleExample(
                    user=example.get("user", ""),
                    assistant=example.get("assistant", ""),
                )
                for example in item.get("examples", [])
            ]
            self.styles[item["id"]] = BotStyle(
                id=item["id"],
                name=item.get("name", ""),
                tone=item.get("tone", ""),
                max_chars=int(item.get("maxChars", 200)),
                emoji_policy=item.get("emojiPolicy", "少用"),
                avoid_words=item.get("avoidWords", []),
                examples=examples,
            )

        self.knowledge_bases = {
            item["id"]: KnowledgeBase(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
                provider=item.get("provider", "maxkb"),
                maxkb_app_id=item.get("maxkbAppId", ""),
                tags=item.get("tags", []),
                priority=int(item.get("priority", 0)),
                fallback_policy=item.get("fallbackPolicy", "clarify"),
                route_examples=item.get("routeExamples", []),
            )
            for item in data.get("knowledgeBases", [])
        }

        self.bindings = [
            GroupBinding(
                group=item["group"],
                bot_id=item["botId"],
                knowledge_base_ids=item.get("knowledgeBaseIds", []),
                reply_triggers=item.get("replyTriggers", []),
            )
            for item in data.get("bindings", [])
        ]

        global_config = data.get("global", {})
        self.exclude_groups = global_config.get("excludeGroups", [])
        self.admins = global_config.get("admins", [])
        self.cooldown_seconds = int(global_config.get("cooldownSeconds", 30))
        self.smart_detection = bool(global_config.get("smartDetection", False))

        self.group_map.clear()
        for binding in self.bindings:
            bot = self._required(self.bot_profiles, binding.bot_id, "botProfile")
            style = self._required(self.styles, bot.style_id, "style")
            knowledge_bases = [
                self._required(self.knowledge_bases, kb_id, "knowledgeBase")
                for kb_id in binding.knowledge_base_ids
            ]
            self.group_map[binding.group] = RuntimeBotConfig(
                group=binding.group,
                bot=bot,
                style=style,
                knowledge_bases=knowledge_bases,
                reply_triggers=binding.reply_triggers,
            )

        logger.info(
            "机器人配置加载完成: %s 个机器人, %s 个风格, %s 个知识库, %s 个群绑定",
            len(self.bot_profiles),
            len(self.styles),
            len(self.knowledge_bases),
            len(self.group_map),
        )

    def restrict_to_group(self, group_name: str) -> None:
        self.restrict_to_groups([group_name])

    def restrict_to_groups(self, group_names: list[str] | tuple[str, ...]) -> None:
        targets = tuple(dict.fromkeys(
            str(group_name).strip()
            for group_name in group_names
            if str(group_name).strip()
        ))
        missing = [target for target in targets if target not in self.group_map]
        if missing:
            raise ValueError(
                f"LISTEN_GROUPS 中的群未在 bindings 中配置: {missing}；"
                f"当前群: {list(self.group_map)}"
            )
        self.group_map = {
            target: self.group_map[target]
            for target in targets
        }
        self.bindings = [
            binding for binding in self.bindings if binding.group in targets
        ]
        allowed_kb_ids = {
            kb_id
            for runtime in self.group_map.values()
            for kb_id in runtime.knowledge_base_ids
        }
        self.knowledge_bases = {
            kb_id: kb
            for kb_id, kb in self.knowledge_bases.items()
            if kb_id in allowed_kb_ids
        }

    @staticmethod
    def _required(source: dict, item_id: str, item_type: str):
        if item_id not in source:
            raise ValueError(f"配置错误: {item_type} 不存在: {item_id}")
        return source[item_id]

    def get_course(self, group_name: str) -> RuntimeBotConfig | None:
        return self.group_map.get(group_name)

    def is_excluded(self, group_name: str) -> bool:
        return group_name in self.exclude_groups

    def is_admin(self, name: str) -> bool:
        return name in self.admins
