import unittest

from ai_ta_bot.knowledge.retriever import KeywordRetriever


class KeywordRetrieverTests(unittest.TestCase):
    def test_priority_does_not_create_false_match(self):
        retriever = KeywordRetriever()
        retriever.load_knowledge_base(
            "kb",
            [
                {
                    "chunk_id": "1",
                    "content": "这是副业项目和小红书获客资料",
                    "priority": 100,
                    "kb_tags": ["副业"],
                    "source": "source.md",
                    "title": "",
                }
            ],
        )

        self.assertEqual(
            retriever.search(["kb"], "量子色动力学拉格朗日量子化", top_k=3),
            [],
        )

    def test_priority_only_breaks_ties_after_match(self):
        retriever = KeywordRetriever()
        retriever.load_knowledge_base(
            "kb",
            [
                {
                    "chunk_id": "low",
                    "content": "小红书获客方法",
                    "priority": 1,
                    "kb_tags": [],
                    "source": "low.md",
                    "title": "",
                },
                {
                    "chunk_id": "high",
                    "content": "小红书获客方法",
                    "priority": 10,
                    "kb_tags": [],
                    "source": "high.md",
                    "title": "",
                },
            ],
        )

        rows = retriever.search(["kb"], "小红书获客", top_k=2)
        self.assertEqual([row["chunk_id"] for row in rows], ["high", "low"])


if __name__ == "__main__":
    unittest.main()
