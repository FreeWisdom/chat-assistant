"""
机器人配置管理模块
加载 botProfiles / styles / knowledgeBases / bindings，维护 群名 -> 运行时配置 的映射。
"""
from dataclasses import dataclass, field
import logging
import yaml

logger = logging.getLogger(__name__)


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
    path: str
    provider: str = "local_files"
    tags: list[str] = field(default_factory=list)
    priority: int = 0
    fallback_policy: str = "clarify"
    route_examples: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    sitemap: str = ""
    credential: str = ""


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


class CourseManager:
    """保留旧类名，内部管理新版机器人配置。"""

    def __init__(self):
        self.bot_profiles: dict[str, BotProfile] = {}
        self.styles: dict[str, BotStyle] = {}
        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        self.bindings: list[GroupBinding] = []
        self.group_map: dict[str, RuntimeBotConfig] = {}
        self.exclude_groups: list[str] = []
        self.admins: list[str] = []
        self.cooldown_seconds: int = 30
        self.smart_detection: bool = True

    @property
    def courses(self) -> list[RuntimeBotConfig]:
        """兼容旧入口：main.py 仍可遍历 cm.courses 加载知识库。"""
        return list(self.group_map.values())

    def load(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if "botProfiles" not in data:
            data = self._from_legacy_courses(data)

        self._load_v2(data)

    def _load_v2(self, data: dict):
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
                StyleExample(user=ex.get("user", ""), assistant=ex.get("assistant", ""))
                for ex in item.get("examples", [])
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
                path=item.get("path", ""),
                provider=item.get("provider", "local_files"),
                tags=item.get("tags", []),
                priority=int(item.get("priority", 0)),
                fallback_policy=item.get("fallbackPolicy", "clarify"),
                route_examples=item.get("routeExamples", []),
                urls=item.get("urls", []),
                sitemap=item.get("sitemap", ""),
                credential=item.get("credential", ""),
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

        global_cfg = data.get("global", {})
        self.exclude_groups = global_cfg.get("excludeGroups", [])
        self.admins = global_cfg.get("admins", [])
        self.cooldown_seconds = global_cfg.get("cooldownSeconds", 30)
        self.smart_detection = global_cfg.get("smartDetection", True)

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
        for group, runtime in self.group_map.items():
            kb_names = ", ".join(kb.name for kb in runtime.knowledge_bases)
            logger.info("  - %s -> %s / %s", group, runtime.bot.name, kb_names)

    def _from_legacy_courses(self, data: dict) -> dict:
        """兼容旧版 courses.yaml，便于已有配置平滑迁移。"""
        bot_profiles = []
        styles = []
        knowledge_bases = []
        bindings = []

        for course in data.get("courses", []):
            course_id = course["id"]
            style_id = f"{course_id}-style"
            bot_profiles.append({
                "id": course_id,
                "name": course.get("name", course_id),
                "role": course.get("description", ""),
                "styleId": style_id,
                "answerPolicyId": "strict-kb",
                "identityPrompt": course.get("systemPrompt", ""),
            })
            styles.append({
                "id": style_id,
                "name": f"{course.get('name', course_id)}默认风格",
                "tone": "像微信群里的熟人，简短直接，不端着",
                "maxChars": 200,
                "emojiPolicy": "少用",
                "avoidWords": ["根据参考资料", "作为AI", "希望这能帮到你"],
            })
            knowledge_bases.append({
                "id": course_id,
                "name": course.get("name", course_id),
                "description": course.get("description", ""),
                "provider": "local_files",
                "path": course["knowledgePath"],
                "fallbackPolicy": "clarify",
            })
            for group in course.get("groups", []):
                bindings.append({
                    "group": group,
                    "botId": course_id,
                    "knowledgeBaseIds": [course_id],
                    "replyTriggers": course.get("replyTriggers", []),
                })

        return {
            "botProfiles": bot_profiles,
            "styles": styles,
            "knowledgeBases": knowledge_bases,
            "bindings": bindings,
            "global": data.get("global", {}),
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
