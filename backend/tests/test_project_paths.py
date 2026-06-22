import unittest
from pathlib import Path

from ai_ta_bot.configuration import CourseManager
from ai_ta_bot.knowledge.loader import PROJECT_ROOT as LOADER_ROOT
from ai_ta_bot.knowledge.loader import load_knowledge
from ai_ta_bot.knowledge.retriever import PROJECT_ROOT as RETRIEVER_ROOT
from ai_ta_bot.knowledge.retriever import _resolve_runtime_path


ROOT = Path(__file__).resolve().parents[2]


class ProjectPathTests(unittest.TestCase):
    def test_knowledge_modules_use_repository_root(self):
        self.assertEqual(LOADER_ROOT, ROOT)
        self.assertEqual(RETRIEVER_ROOT, ROOT)
        self.assertEqual(
            _resolve_runtime_path("runtime/vector_store"),
            ROOT / "runtime" / "vector_store",
        )

    def test_configured_local_knowledge_base_loads_documents(self):
        manager = CourseManager()
        manager.load(ROOT / "config" / "bot.yaml")

        knowledge_base = manager.knowledge_bases["fuye-projects"]
        loaded = load_knowledge(knowledge_base)

        self.assertGreater(len(loaded.chunks), 0)
        self.assertTrue(
            any(item["source"].endswith(".md") for item in loaded.chunks)
        )
        self.assertTrue(
            any(item["source"].startswith("faq.json#") for item in loaded.chunks)
        )


if __name__ == "__main__":
    unittest.main()
