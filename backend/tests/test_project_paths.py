import unittest
from pathlib import Path

from ai_ta_bot.configuration import CourseManager


ROOT = Path(__file__).resolve().parents[2]


class ProjectPathTests(unittest.TestCase):
    def test_configured_knowledge_bases_are_aliyun_cloud_indexes(self):
        manager = CourseManager()
        manager.load(ROOT / "config" / "bot.yaml")

        self.assertEqual(len(manager.knowledge_bases), 2)
        for knowledge_base in manager.knowledge_bases.values():
            self.assertEqual(
                knowledge_base.provider,
                "aliyun_bailian",
            )
            self.assertTrue(knowledge_base.workspace_id)
            self.assertTrue(knowledge_base.index_id)

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
