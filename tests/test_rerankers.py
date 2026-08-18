from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from dataforge.indexing.rerankers import OpenAIRerankerClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {
                "model": "bge-reranker-large",
                "usage": {"total_tokens": 22},
                "results": [
                    {"index": 0, "relevance_score": 0.98},
                    {"index": 2, "relevance_score": 0.37},
                    {"index": 1, "relevance_score": 0.01},
                ],
            }
        ).encode()


class RerankerClientTest(unittest.TestCase):
    @patch("urllib.request.urlopen", return_value=FakeResponse())
    def test_sorts_and_enforces_top_n_when_service_returns_extra_rows(self, urlopen):
        client = OpenAIRerankerClient(
            {
                "base_url": "http://reranker.test/v1",
                "model": "bge-reranker-large",
                "timeout_seconds": 5,
                "max_retries": 0,
            }
        )

        result = client.rerank(
            "人工智能的应用", ["医学 AI", "机器学习", "AI 改变生活"], top_n=2
        )

        self.assertEqual([item["index"] for item in result["results"]], [0, 2])
        self.assertEqual(result["usage"]["total_tokens"], 22)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://reranker.test/v1/rerank")
        self.assertEqual(json.loads(request.data)["top_n"], 2)


if __name__ == "__main__":
    unittest.main()
