"""
课程管理模块
加载 courses.yaml，维护 群名→课程 的映射
"""
import yaml
import logging

logger = logging.getLogger(__name__)


class Course:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data["name"]
        self.description = data["description"]
        self.groups = data["groups"]  # 微信群名列表
        self.knowledge_path = data["knowledgePath"]
        self.system_prompt = data["systemPrompt"]
        self.reply_triggers = data.get("replyTriggers", [])

    def __repr__(self):
        return f"Course({self.id}, {self.name}, groups={self.groups})"


class CourseManager:
    def __init__(self):
        self.courses: list[Course] = []
        self.group_map: dict[str, Course] = {}
        self.exclude_groups: list[str] = []
        self.admins: list[str] = []
        self.cooldown_seconds: int = 30
        self.smart_detection: bool = True

    def load(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.courses = [Course(c) for c in data["courses"]]
        global_cfg = data.get("global", {})
        self.exclude_groups = global_cfg.get("excludeGroups", [])
        self.admins = global_cfg.get("admins", [])
        self.cooldown_seconds = global_cfg.get("cooldownSeconds", 30)
        self.smart_detection = global_cfg.get("smartDetection", True)

        # 群名 → 课程映射
        self.group_map.clear()
        for course in self.courses:
            for group_name in course.groups:
                self.group_map[group_name] = course

        logger.info(f"课程配置加载完成: {len(self.courses)} 门课程, {len(self.group_map)} 个群")
        for c in self.courses:
            logger.info(f"  - {c.name}: {', '.join(c.groups)}")

    def get_course(self, group_name: str) -> Course | None:
        return self.group_map.get(group_name)

    def is_excluded(self, group_name: str) -> bool:
        return group_name in self.exclude_groups

    def is_admin(self, name: str) -> bool:
        return name in self.admins
