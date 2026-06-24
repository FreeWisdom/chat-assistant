import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_ta_bot.configuration import KnowledgeBase
from ai_ta_bot.knowledge.cloud_knowledge import (
    AliyunBailianKnowledgeClient,
)


class FakeRetrieveRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeModels:
    RetrieveRequest = FakeRetrieveRequest


def make_kb(kb_id="kb-1", priority=0):
    return KnowledgeBase(
        id=kb_id,
        name=f"知识库 {kb_id}",
        description="测试",
        provider="aliyun_bailian",
        workspace_id="workspace-1",
        index_id=f"index-{kb_id}",
        priority=priority,
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def retrieve_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append((workspace_id, request, headers, runtime))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_response(nodes, success=True):
    return SimpleNamespace(
        body=SimpleNamespace(
            success=success,
            request_id="request-1",
            data=SimpleNamespace(nodes=nodes),
        )
    )


class AliyunBailianKnowledgeClientTests(unittest.TestCase):
    def make_client(self, responses, **kwargs):
        fake = FakeClient(responses)
        client = AliyunBailianKnowledgeClient(
            client=fake,
            models_module=FakeModels,
            runtime_factory=lambda: "runtime",
            max_attempts=kwargs.pop("max_attempts", 1),
            **kwargs,
        )
        return client, fake

    def test_retrieves_and_normalizes_nodes(self):
        response = make_response([
            SimpleNamespace(
                text="命中的知识内容",
                score=0.82,
                metadata=(
                    '{"doc_name":"制度文档.pdf",'
                    '"title":"制度说明","doc_id":"doc-1"}'
                ),
            )
        ])
        client, fake = self.make_client([response])

        results = client.search([make_kb()], "请解释制度", top_k=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "命中的知识内容")
        self.assertEqual(results[0]["source"], "制度文档.pdf")
        self.assertEqual(results[0]["kb_id"], "kb-1")
        self.assertEqual(results[0]["_score"], 0.82)
        workspace_id, request, headers, runtime = fake.calls[0]
        self.assertEqual(workspace_id, "workspace-1")
        self.assertEqual(request.index_id, "index-kb-1")
        self.assertEqual(request.query, "请解释制度")
        self.assertTrue(request.enable_reranking)
        self.assertEqual(request.dense_similarity_top_k, 20)
        self.assertEqual(request.sparse_similarity_top_k, 20)
        self.assertEqual(request.rerank_min_score, 0.2)
        self.assertEqual(request.rerank_top_n, 5)
        self.assertEqual(headers, {})
        self.assertEqual(runtime, "runtime")

    def test_filters_low_scores_and_sorts_across_cloud_indexes(self):
        response_a = make_response([
            SimpleNamespace(text="低分", score=0.1, metadata={}),
            SimpleNamespace(text="中分", score=0.6, metadata={}),
        ])
        response_b = make_response([
            SimpleNamespace(text="高分", score=0.9, metadata={}),
        ])
        client, _ = self.make_client(
            [response_a, response_b],
            min_score=0.2,
        )

        results = client.search(
            [make_kb("a"), make_kb("b")],
            "问题",
            top_k=2,
        )

        self.assertEqual(
            [item["content"] for item in results],
            ["高分", "中分"],
        )

    def test_retries_transient_failure(self):
        response = make_response([
            SimpleNamespace(text="恢复后的结果", score=0.8, metadata={}),
        ])
        client, fake = self.make_client(
            [RuntimeError("temporary"), response],
            max_attempts=2,
        )

        with patch("ai_ta_bot.knowledge.cloud_knowledge.time.sleep"):
            results = client.search([make_kb()], "问题")

        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(results[0]["content"], "恢复后的结果")

    def test_rejects_non_cloud_or_incomplete_config(self):
        client, _ = self.make_client([])
        invalid_provider = make_kb()
        invalid_provider.provider = "local_files"
        with self.assertRaisesRegex(ValueError, "只支持阿里云百炼"):
            client.validate([invalid_provider])

        incomplete = make_kb()
        incomplete.index_id = ""
        with self.assertRaisesRegex(ValueError, "缺少 workspaceId 或 indexId"):
            client.validate([incomplete])


if __name__ == "__main__":
    unittest.main()
