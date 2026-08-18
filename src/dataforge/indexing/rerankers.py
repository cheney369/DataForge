from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from ..errors import ValidationError


class OpenAIRerankerClient:
    """Small adapter for Jina/OpenAI-style ``POST /rerank`` services."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def test(self) -> dict[str, Any]:
        result = self.rerank(
            "人工智能的应用",
            ["人工智能在医学上的应用", "机器学习与深度学习的区别"],
            top_n=1,
        )
        return {
            "status": "ready",
            "model": result["model"],
            "latency_ms": result["latency_ms"],
        }

    def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValidationError("Reranker query 不能为空")
        if not documents:
            return {
                "model": self.config["model"],
                "results": [],
                "usage": {},
                "latency_ms": 0,
            }
        limit = min(len(documents), max(1, int(top_n)))
        base_url = str(self.config["base_url"]).rstrip("/")
        url = base_url if base_url.endswith("/rerank") else f"{base_url}/rerank"
        payload = json.dumps(
            {
                "model": self.config["model"],
                "query": query.strip(),
                "documents": documents,
                "top_n": limit,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key_ref = str(self.config.get("api_key_env") or "").strip()
        if key_ref and os.getenv(key_ref):
            headers["Authorization"] = f"Bearer {os.environ[key_ref]}"
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        attempts = max(1, int(self.config.get("max_retries") or 0) + 1)
        started = time.monotonic()
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                with urllib.request.urlopen(
                    request, timeout=float(self.config.get("timeout_seconds") or 30)
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                raw_results = body.get("results") or body.get("data") or []
                if not isinstance(raw_results, list):
                    raise ValidationError("Reranker 服务未返回 results 数组")
                parsed: list[dict[str, Any]] = []
                seen: set[int] = set()
                for item in raw_results:
                    index = int(item.get("index", -1))
                    score = item.get("relevance_score", item.get("score"))
                    if index < 0 or index >= len(documents) or score is None or index in seen:
                        continue
                    seen.add(index)
                    parsed.append({"index": index, "relevance_score": float(score)})
                if not parsed:
                    raise ValidationError("Reranker 服务没有返回有效排序结果")
                parsed.sort(key=lambda item: item["relevance_score"], reverse=True)
                return {
                    "model": str(body.get("model") or self.config["model"]),
                    "results": parsed[:limit],
                    "usage": body.get("usage") or {},
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
                ValidationError,
            ) as exc:
                last_error = exc
        raise ValidationError(f"Reranker 服务调用失败：{last_error}")
