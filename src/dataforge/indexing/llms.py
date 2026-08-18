from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from ..errors import ValidationError


class OpenAIChatClient:
    """Small OpenAI-compatible probe used by the configurable resource registry."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def test(self) -> dict[str, Any]:
        result = self.complete(
            [{"role": "user", "content": "只回复 OK"}],
            temperature=0,
            max_tokens=8,
        )
        return {
            "status": "ready",
            "model": result["model"],
            "latency_ms": result["latency_ms"],
        }

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        if not messages:
            raise ValidationError("LLM 请求至少需要一条消息")
        base_url = str(self.config["base_url"]).rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = json.dumps(
            {
                "model": self.config["model"],
                "messages": messages,
                "temperature": max(0.0, min(2.0, float(temperature))),
                "max_tokens": max(1, min(32768, int(max_tokens))),
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
                    request, timeout=float(self.config.get("timeout_seconds") or 60)
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                choices = body.get("choices") or []
                if not choices:
                    raise ValidationError("LLM 服务未返回 choices")
                choice = choices[0]
                message = choice.get("message") or {}
                content = str(message.get("content") or "")
                if not content.strip():
                    raise ValidationError("LLM 服务返回了空内容")
                return {
                    "content": content,
                    "model": str(body.get("model") or self.config["model"]),
                    "finish_reason": choice.get("finish_reason"),
                    "usage": body.get("usage") or {},
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
        raise ValidationError(f"LLM 服务调用失败：{last_error}")

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Iterator[dict[str, Any]]:
        """Yield OpenAI-compatible content deltas followed by one completion event."""
        if not messages:
            raise ValidationError("LLM 请求至少需要一条消息")
        base_url = str(self.config["base_url"]).rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = json.dumps(
            {
                "model": self.config["model"],
                "messages": messages,
                "temperature": max(0.0, min(2.0, float(temperature))),
                "max_tokens": max(1, min(32768, int(max_tokens))),
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        key_ref = str(self.config.get("api_key_env") or "").strip()
        if key_ref and os.getenv(key_ref):
            headers["Authorization"] = f"Bearer {os.environ[key_ref]}"
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        attempts = max(1, int(self.config.get("max_retries") or 0) + 1)
        started = time.monotonic()
        last_error: Exception | None = None
        for _ in range(attempts):
            emitted = False
            content_parts: list[str] = []
            model = str(self.config["model"])
            finish_reason: str | None = None
            usage: dict[str, Any] = {}
            try:
                with urllib.request.urlopen(
                    request, timeout=float(self.config.get("timeout_seconds") or 60)
                ) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        chunk = json.loads(data)
                        model = str(chunk.get("model") or model)
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        finish_reason = choice.get("finish_reason") or finish_reason
                        delta = str((choice.get("delta") or {}).get("content") or "")
                        if delta:
                            emitted = True
                            content_parts.append(delta)
                            yield {"type": "delta", "content": delta}
                content = "".join(content_parts)
                if not content.strip():
                    raise ValidationError("LLM 服务返回了空内容")
                yield {
                    "type": "complete",
                    "content": content,
                    "model": model,
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
                return
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if emitted:
                    break
        raise ValidationError(f"LLM 流式调用失败：{last_error}")
