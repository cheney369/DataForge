from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..errors import ValidationError


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    tokens: int
    model: str


class OpenAIEmbeddingClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch([], 0, self.config["model"])
        base_url = str(self.config["base_url"]).rstrip("/")
        url = base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"
        payload = json.dumps(
            {"model": self.config["model"], "input": texts},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key_ref = str(self.config.get("api_key_env") or "").strip()
        if key_ref and os.getenv(key_ref):
            headers["Authorization"] = f"Bearer {os.environ[key_ref]}"
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        attempts = max(1, int(self.config.get("max_retries") or 0) + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=float(self.config.get("timeout_seconds") or 30),
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                data = sorted(body.get("data") or [], key=lambda item: item.get("index", 0))
                vectors = [item.get("embedding") or [] for item in data]
                if len(vectors) != len(texts) or any(not vector for vector in vectors):
                    raise ValidationError("Embedding 服务返回数量或向量内容不正确")
                dimensions = {len(vector) for vector in vectors}
                if len(dimensions) != 1:
                    raise ValidationError("Embedding 服务返回的向量维度不一致")
                configured = int(self.config.get("dimension") or 0)
                actual = dimensions.pop()
                if configured and configured != actual:
                    raise ValidationError(
                        f"Embedding 维度不匹配：配置 {configured}，实际 {actual}"
                    )
                usage = body.get("usage") or {}
                return EmbeddingBatch(
                    [[float(value) for value in vector] for vector in vectors],
                    int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0),
                    str(body.get("model") or self.config["model"]),
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(2**attempt, 4))
        raise ValidationError(f"Embedding 服务调用失败：{last_error}")

    def test(self) -> dict[str, Any]:
        started = time.monotonic()
        batch = self.embed(["DataForge 向量服务连接测试"])
        return {
            "status": "ready",
            "model": batch.model,
            "dimension": len(batch.vectors[0]),
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
