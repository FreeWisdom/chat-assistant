import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ta_bot.configuration import CourseManager


ROOT = Path(__file__).resolve().parents[2]


class ProjectPathTests(unittest.TestCase):
    def test_placeholder_cloud_ids_are_not_treated_as_runtime_config(self):
        with patch(
            "ai_ta_bot.configuration.loader.config.ALIYUN_BAILIAN_WORKSPACE_ID",
            "",
        ):
            manager = CourseManager()
            manager.load(ROOT / "config" / "bot.yaml")

        placeholder_ids = {"fuye-projects", "food-checkin"}
        self.assertTrue(
            placeholder_ids.issubset(manager.knowledge_bases),
        )
        for knowledge_base_id in placeholder_ids:
            knowledge_base = manager.knowledge_bases[knowledge_base_id]
            self.assertEqual(
                knowledge_base.provider,
                "maxkb",
            )
            self.assertTrue(knowledge_base.maxkb_app_id.startswith("your-"))

        configured = [
            knowledge_base
            for knowledge_base_id, knowledge_base
            in manager.knowledge_bases.items()
            if knowledge_base_id not in placeholder_ids
        ]
        self.assertTrue(configured)
        for knowledge_base in configured:
            self.assertTrue(knowledge_base.maxkb_app_id)

    def test_two_approved_groups_use_hand_raise_and_separate_knowledge_bases(self):
        manager = CourseManager()
        manager.load(ROOT / "config" / "bot.yaml")
        manager.restrict_to_groups(("项目研究", "每日饮食打卡🍽️"))

        self.assertEqual(
            set(manager.group_map),
            {"项目研究", "每日饮食打卡🍽️"},
        )
        self.assertEqual(
            manager.group_map["项目研究"].knowledge_base_ids,
            ["fuye-projects"],
        )
        self.assertEqual(
            manager.group_map["项目研究"].style.id,
            "practical-friend",
        )
        self.assertEqual(
            manager.group_map["每日饮食打卡🍽️"].knowledge_base_ids,
            ["food-checkin"],
        )
        self.assertEqual(
            manager.group_map["每日饮食打卡🍽️"].style.id,
            "food-friend",
        )
        for runtime in manager.group_map.values():
            self.assertIn("#举手", runtime.reply_triggers)


if __name__ == "__main__":
    unittest.main()
