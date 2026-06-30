"""Typed runtime configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StyleExample:
    user: str
    assistant: str


@dataclass
class BotStyle:
    id: str
    name: str = ""
    tone: str = ""
    max_chars: int = 200
    emoji_policy: str = "少用"
    avoid_words: list[str] = field(default_factory=list)
    examples: list[StyleExample] = field(default_factory=list)


@dataclass
class KnowledgeBase:
    id: str
    name: str
    description: str
    provider: str = "maxkb"
    # MaxKB fields
    maxkb_app_id: str = ""
    tags: list[str] = field(default_factory=list)
    priority: int = 0
    fallback_policy: str = "clarify"
    route_examples: list[str] = field(default_factory=list)


@dataclass
class BotProfile:
    id: str
    name: str
    role: str
    style_id: str
    answer_policy_id: str = "strict-kb"
    responsibilities: list[str] = field(default_factory=list)
    identity_prompt: str = ""


@dataclass
class GroupBinding:
    group: str
    bot_id: str
    knowledge_base_ids: list[str]
    reply_triggers: list[str] = field(default_factory=list)


@dataclass
class RuntimeBotConfig:
    group: str
    bot: BotProfile
    style: BotStyle
    knowledge_bases: list[KnowledgeBase]
    reply_triggers: list[str]

    @property
    def id(self) -> str:
        return self.bot.id

    @property
    def name(self) -> str:
        return self.bot.name

    @property
    def knowledge_base_ids(self) -> list[str]:
        return [kb.id for kb in self.knowledge_bases]
