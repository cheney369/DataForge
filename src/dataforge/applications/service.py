from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Iterator
from typing import Any, TYPE_CHECKING

from ..errors import AuthenticationError, ValidationError
from ..indexing.llms import OpenAIChatClient
from .contracts import (
    normalize_contract,
    render_template,
    template_variables,
    validate_instance,
    value_at_path,
)
from .repository import AIApplicationRepository

if TYPE_CHECKING:
    from ..application import DataForge


APP_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
ALLOWED_ROLES = {"user", "assistant"}


class AIApplicationService:
    def __init__(self, dataforge: DataForge):
        self.dataforge = dataforge
        self.repository = AIApplicationRepository(dataforge.store)
        self.repository.initialize()

    def create_application(self, app_key: str, name: str, description: str) -> dict[str, Any]:
        key = app_key.strip()
        if not APP_KEY.fullmatch(key):
            raise ValidationError("AI 应用标识需为 3-64 位小写字母、数字或连字符")
        if not name.strip():
            raise ValidationError("请填写 AI 应用名称")
        return self.repository.create_application(key, name, description)

    def create_version(
        self,
        application_id: str,
        binding_id: str,
        llm_service_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        self.dataforge.delivery.repository.get_binding(binding_id)
        llm = self.dataforge.indexing.repository.get_llm_service(llm_service_id)
        if not llm["active"]:
            raise ValidationError("只能选择当前生效的 LLM 服务")
        normalized = self._normalize_config(config)
        return self.repository.create_version(
            application_id, binding_id, llm_service_id, normalized
        )

    def publish_version(self, version_id: str) -> dict[str, Any]:
        version = self._normalized_version(self.repository.get_version(version_id))
        binding = self.dataforge.delivery.repository.get_binding(
            version["application_binding_id"]
        )
        resolved = self.dataforge.delivery.resolve_binding_version(binding)
        llm = self.dataforge.indexing.test_llm_service(version["llm_service_id"])
        if llm["status"] != "ready":
            raise ValidationError(
                f"LLM 服务未就绪：{llm.get('last_test', {}).get('error', '连接失败')}"
            )
        validation = {
            "passed": True,
            "binding_key": binding["binding_key"],
            "resolved_collection_version_id": resolved["id"],
            "contract": {
                "input_schema": version["config"]["input_schema"],
                "output_schema": version["config"]["output_schema"],
                "query_field": version["config"]["query_field"],
            },
            "llm": self._llm_snapshot(llm),
        }
        return self.repository.publish_version(version_id, validation)

    def create_credential(self, application_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("请填写调用密钥名称")
        random_part = secrets.token_urlsafe(32)
        token = f"dfk_{secrets.token_hex(4)}_{random_part}"
        credential = self.repository.create_credential(
            application_id,
            name,
            f"{token[:16]}…",
            self._hash_token(token),
        )
        return {**credential, "api_key": token}

    def revoke_credential(self, credential_id: str) -> dict[str, Any]:
        return self.repository.revoke_credential(credential_id)

    def invoke(
        self,
        app_key: str,
        api_key: str,
        inputs: dict[str, Any],
        *,
        version_number: int | None = None,
        history: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_invocation(
            app_key,
            inputs,
            api_key=api_key,
            version_number=version_number,
            history=history,
            filters=filters,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
        )
        return self._execute(prepared, include_retrieval=False)

    def invoke_stream(
        self,
        app_key: str,
        api_key: str,
        inputs: dict[str, Any],
        *,
        version_number: int | None = None,
        history: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        prepared = self.prepare_invocation(
            app_key,
            inputs,
            api_key=api_key,
            version_number=version_number,
            history=history,
            filters=filters,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
        )
        return self._execute_stream(prepared)

    def preview_version(
        self,
        version_id: str,
        inputs: dict[str, Any],
        *,
        history: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        version = self._normalized_version(self.repository.get_version(version_id))
        application = self.repository.get_application(version["application_id"])
        prepared = self._prepare(
            application,
            version,
            inputs,
            credential=None,
            history=history,
            filters=filters,
            session_id=None,
            user_id=None,
            metadata={"source": "dataforge-preview"},
            mode="preview",
        )
        return self._execute(prepared, include_retrieval=True)

    def published_config(
        self, app_key: str, version_number: int | None = None
    ) -> dict[str, Any]:
        """Return the immutable, secret-free configuration consumed by business apps."""
        application = self.repository.get_application(app_key)
        if not application["active"]:
            raise ValidationError("应用配置已停用")
        version = self._normalized_version(
            self.repository.get_published_version(application["id"], version_number)
            if version_number is not None
            else self.repository.get_current_version(application["id"])
        )
        binding = self.dataforge.delivery.repository.get_binding(
            version["application_binding_id"]
        )
        collection_version = self.dataforge.delivery.resolve_binding_version(binding)
        retrieval = self.dataforge.indexing.repository.get_retrieval_profile(
            collection_version["retrieval_profile_id"]
        )
        llm = self._runtime_llm(version)
        config = version["config"]
        return {
            "schema_version": "dataforge.application-config/v1",
            "application": {
                "key": application["app_key"],
                "name": application["name"],
                "description": application["description"],
            },
            "release": {
                "version": version["version"],
                "published_at": version["published_at"],
                "is_current": version["is_current"],
            },
            "knowledge": {
                "binding_key": binding["binding_key"],
                "version_policy": "latest" if binding["follow_latest"] else "pinned",
                "collection_id": collection_version["collection_id"],
                "collection_name": collection_version["collection_name"],
                "collection_version_id": collection_version["id"],
                "collection_version": collection_version["version"],
            },
            "retrieval": {
                "profile_id": retrieval["id"],
                "profile_name": retrieval["name"],
                "profile_version": retrieval["version"],
                "config": retrieval["config"],
                "top_k": config["top_k"],
                "query_field": config["query_field"],
                "allowed_filter_fields": config["allowed_filter_fields"],
                "include_citations": config["include_citations"],
            },
            "prompt": {
                "system": config["system_prompt"],
                "user": config["user_prompt"],
                "variables": config["prompt_variables"],
            },
            "generation": {
                "temperature": config["temperature"],
                "max_tokens": config["max_tokens"],
            },
            "model": {
                "provider": llm["provider"],
                "base_url": llm["base_url"],
                "model": llm["model"],
                "timeout_seconds": llm["timeout_seconds"],
                "max_retries": llm["max_retries"],
                "api_key_env": llm.get("api_key_env"),
            },
            "contract": {
                "input_schema": config["input_schema"],
                "output_schema": config["output_schema"],
            },
        }

    def chat(
        self,
        app_key: str,
        message: str,
        *,
        history: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Backward-compatible Studio playground endpoint."""
        application = self.repository.get_application(app_key)
        version = self._normalized_version(
            self.repository.get_current_version(application["id"])
        )
        prepared = self._prepare(
            application,
            version,
            self._query_inputs(version["config"]["query_field"], message),
            credential=None,
            history=history,
            filters=filters,
            session_id=None,
            user_id=None,
            metadata={"source": "dataforge-chat-playground"},
            mode="preview",
            top_k=top_k,
        )
        return self._execute(prepared, include_retrieval=True)

    def prepare_invocation(
        self,
        app_key: str,
        inputs: dict[str, Any],
        *,
        api_key: str,
        version_number: int | None,
        history: list[dict[str, str]] | None,
        filters: dict[str, Any] | None,
        session_id: str | None,
        user_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        application = self.repository.get_application(app_key)
        credential = self._authenticate(api_key, application)
        version = self._normalized_version(
            self.repository.get_published_version(application["id"], version_number)
            if version_number is not None
            else self.repository.get_current_version(application["id"])
        )
        return self._prepare(
            application,
            version,
            inputs,
            credential=credential,
            history=history,
            filters=filters,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            mode="pinned" if version_number is not None else "production",
        )

    def _prepare(
        self,
        application: dict[str, Any],
        version: dict[str, Any],
        inputs: dict[str, Any],
        *,
        credential: dict[str, Any] | None,
        history: list[dict[str, str]] | None,
        filters: dict[str, Any] | None,
        session_id: str | None,
        user_id: str | None,
        metadata: dict[str, Any] | None,
        mode: str,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        if not application["active"]:
            raise ValidationError("AI 应用已停用")
        version = self._normalized_version(version)
        config = version["config"]
        if len(json.dumps(inputs, ensure_ascii=False)) > 65_536:
            raise ValidationError("inputs 不能超过 64 KiB")
        if len(json.dumps(metadata or {}, ensure_ascii=False)) > 16_384:
            raise ValidationError("metadata 不能超过 16 KiB")
        validate_instance(inputs, config["input_schema"])
        query = value_at_path(inputs, config["query_field"])
        if not str(query).strip():
            raise ValidationError("检索问题字段不能为空")
        if len(str(query)) > 16_384:
            raise ValidationError("检索问题字段不能超过 16 KiB")
        clean_filters = filters or {}
        unknown_filters = sorted(set(clean_filters) - set(config["allowed_filter_fields"]))
        if unknown_filters:
            raise ValidationError(f"应用版本未开放过滤字段：{'、'.join(unknown_filters)}")
        clean_history = self._validate_history(history or [])
        return {
            "application": application,
            "version": version,
            "credential": credential,
            "inputs": inputs,
            "query": str(query).strip(),
            "history": clean_history,
            "filters": clean_filters,
            "top_k": top_k or config["top_k"],
            "session_id": self._bounded_identifier(session_id, "session_id"),
            "user_id": self._bounded_identifier(user_id, "user_id"),
            "metadata": metadata or {},
            "mode": mode,
        }

    def _execute(self, prepared: dict[str, Any], *, include_retrieval: bool) -> dict[str, Any]:
        run = self._create_run(prepared)
        try:
            retrieval = self._retrieve(prepared)
            messages = self._messages(prepared, retrieval)
            completion = OpenAIChatClient(self._runtime_llm(prepared["version"])).complete(
                messages,
                temperature=prepared["version"]["config"]["temperature"],
                max_tokens=prepared["version"]["config"]["max_tokens"],
            )
            return self._finish(
                run,
                prepared,
                retrieval,
                {
                    "answer": completion["content"],
                    "model": completion["model"],
                    "finish_reason": completion["finish_reason"],
                    "usage": completion["usage"],
                    "llm_latency_ms": completion["latency_ms"],
                },
                include_retrieval=include_retrieval,
            )
        except Exception as error:
            self.repository.fail_run(run["id"], str(error))
            raise

    def _execute_stream(self, prepared: dict[str, Any]) -> Iterator[dict[str, Any]]:
        run = self._create_run(prepared)
        completed_run = False
        try:
            yield {
                "event": "start",
                "data": {
                    "request_id": run["id"],
                    "application": prepared["application"]["app_key"],
                    "version": prepared["version"]["version"],
                },
            }
            retrieval = self._retrieve(prepared)
            yield {
                "event": "retrieval",
                "data": {
                    "request_id": run["id"],
                    "result_count": len(retrieval["results"]),
                    "citations": self._citations(retrieval)
                    if prepared["version"]["config"]["include_citations"] else [],
                },
            }
            messages = self._messages(prepared, retrieval)
            completion: dict[str, Any] | None = None
            for event in OpenAIChatClient(self._runtime_llm(prepared["version"])).stream(
                messages,
                temperature=prepared["version"]["config"]["temperature"],
                max_tokens=prepared["version"]["config"]["max_tokens"],
            ):
                if event["type"] == "delta":
                    yield {"event": "delta", "data": {"text": event["content"]}}
                else:
                    completion = event
            if completion is None:
                raise ValidationError("LLM 流式调用没有完成事件")
            response = self._finish(
                run,
                prepared,
                retrieval,
                {
                    "answer": completion["content"],
                    "model": completion["model"],
                    "finish_reason": completion["finish_reason"],
                    "usage": completion["usage"],
                    "llm_latency_ms": completion["latency_ms"],
                },
                include_retrieval=False,
            )
            completed_run = True
            yield {"event": "complete", "data": response}
        except GeneratorExit:
            if not completed_run:
                self.repository.fail_run(run["id"], "SSE 客户端已断开")
            raise
        except Exception as error:
            self.repository.fail_run(run["id"], str(error))
            yield {
                "event": "error",
                "data": {"request_id": run["id"], "error": type(error).__name__, "message": str(error)},
            }

    def _create_run(self, prepared: dict[str, Any]) -> dict[str, Any]:
        credential = prepared["credential"]
        request = {
            "mode": prepared["mode"],
            "inputs": prepared["inputs"],
            "filters": prepared["filters"],
            "history": prepared["history"],
            "session_id": prepared["session_id"],
            "user_id": prepared["user_id"],
            "metadata": prepared["metadata"],
            "credential_id": credential["id"] if credential else None,
        }
        return self.repository.create_run(
            prepared["application"]["id"],
            prepared["version"]["id"],
            prepared["query"],
            request,
        )

    def _retrieve(self, prepared: dict[str, Any]) -> dict[str, Any]:
        version = prepared["version"]
        return self.dataforge.delivery.query_binding(
            version["binding_key"],
            prepared["query"],
            filters=prepared["filters"],
            top_k=prepared["top_k"],
        )

    def _messages(
        self, prepared: dict[str, Any], retrieval: dict[str, Any]
    ) -> list[dict[str, str]]:
        config = prepared["version"]["config"]
        variables: dict[str, Any] = {"context": retrieval["context"]}
        for name, path in config["prompt_variables"].items():
            variables[name] = value_at_path(prepared["inputs"], path)
        return [
            {"role": "system", "content": render_template(config["system_prompt"], variables)},
            *prepared["history"],
            {"role": "user", "content": render_template(config["user_prompt"], variables)},
        ]

    def _finish(
        self,
        run: dict[str, Any],
        prepared: dict[str, Any],
        retrieval: dict[str, Any],
        completion: dict[str, Any],
        *,
        include_retrieval: bool,
    ) -> dict[str, Any]:
        output = {"answer": completion["answer"]}
        validate_instance(output, prepared["version"]["config"]["output_schema"], "output")
        citations = (
            self._citations(retrieval)
            if prepared["version"]["config"]["include_citations"] else []
        )
        stored_response = {**completion, "output": output, "citations": citations}
        completed = self.repository.complete_run(
            run["id"],
            retrieval["collection"]["version_id"],
            self._retrieval_audit(retrieval),
            stored_response,
        )
        response = {
            "request_id": completed["id"],
            "run_id": completed["id"],
            "application": {
                "id": prepared["application"]["id"],
                "key": prepared["application"]["app_key"],
                "name": prepared["application"]["name"],
                "version": prepared["version"]["version"],
            },
            "output": output,
            "answer": completion["answer"],
            "citations": citations,
            "model": completion["model"],
            "finish_reason": completion["finish_reason"],
            "usage": completion["usage"],
            "llm_latency_ms": completion["llm_latency_ms"],
        }
        if include_retrieval:
            response["retrieval"] = retrieval
        return response

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        system_prompt = str(config.get("system_prompt") or "").strip()
        user_prompt = str(config.get("user_prompt") or "").strip()
        if not system_prompt or not user_prompt:
            raise ValidationError("System Prompt 和 User Prompt 不能为空")
        contract = normalize_contract(config)
        declared = template_variables(system_prompt, user_prompt)
        if "context" not in declared:
            raise ValidationError("Prompt 必须引用 {{ context }}")
        unknown = sorted(declared - {"context"} - set(contract["prompt_variables"]))
        if unknown:
            raise ValidationError(f"Prompt 变量尚未映射到输入字段：{'、'.join(unknown)}")
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": max(0.0, min(2.0, float(config.get("temperature", 0.2)))),
            "max_tokens": max(1, min(32768, int(config.get("max_tokens") or 1024))),
            "top_k": max(1, min(100, int(config.get("top_k") or 5))),
            **contract,
        }

    def _normalized_version(self, version: dict[str, Any]) -> dict[str, Any]:
        return {**version, "config": self._normalize_config(version["config"])}

    @staticmethod
    def _query_inputs(path: str, message: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        current = result
        parts = path.split(".")
        for part in parts[:-1]:
            nested: dict[str, Any] = {}
            current[part] = nested
            current = nested
        current[parts[-1]] = message
        return result

    def _authenticate(
        self, api_key: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        token = (api_key or "").strip()
        if not token:
            raise AuthenticationError("缺少应用调用密钥")
        credential = self.repository.authenticate_credential(self._hash_token(token))
        if not credential or credential["application_id"] != application["id"]:
            raise AuthenticationError("应用调用密钥无效或已撤销")
        if not credential["application_active"]:
            raise AuthenticationError("AI 应用已停用")
        return credential

    def _runtime_llm(self, version: dict[str, Any]) -> dict[str, Any]:
        if version["status"] == "published" and version["validation"].get("llm"):
            return version["validation"]["llm"]
        llm = self.dataforge.indexing.repository.get_llm_service(version["llm_service_id"])
        if not llm["active"]:
            raise ValidationError("草稿版本引用的 LLM 服务已停用")
        return self._llm_snapshot(llm)

    @staticmethod
    def _llm_snapshot(llm: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": llm["id"],
            "name": llm["name"],
            "provider": llm["provider"],
            "base_url": llm["base_url"],
            "model": llm["model"],
            "timeout_seconds": llm["timeout_seconds"],
            "max_retries": llm["max_retries"],
            "api_key_env": llm.get("api_key_env"),
        }

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _validate_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        if len(history) > 20:
            raise ValidationError("单次请求最多携带 20 条历史消息")
        result = []
        for item in history:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role not in ALLOWED_ROLES or not content:
                raise ValidationError("历史消息只允许非空的 user / assistant 消息")
            if len(content) > 16_384:
                raise ValidationError("单条历史消息不能超过 16 KiB")
            result.append({"role": role, "content": content})
        return result

    @staticmethod
    def _bounded_identifier(value: str | None, name: str) -> str | None:
        cleaned = (value or "").strip()
        if len(cleaned) > 128:
            raise ValidationError(f"{name} 不能超过 128 个字符")
        return cleaned or None

    @staticmethod
    def _citations(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": item["index_record_id"],
                "score": item["score"],
                "vector_score": item.get("vector_score"),
                "rerank_score": item.get("rerank_score"),
                "content": item["context"],
                "source": item["source"],
                "knowledge": item["collection_member"],
            }
            for item in retrieval["results"]
        ]

    @staticmethod
    def _retrieval_audit(retrieval: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": retrieval["query"],
            "collection": retrieval["collection"],
            "retrieval_profile": retrieval["retrieval_profile"],
            "application_binding": retrieval["application_binding"],
            "reranker": retrieval.get("reranker", {"enabled": False}),
            "result_count": len(retrieval["results"]),
            "results": [
                {
                    "index_record_id": item["index_record_id"],
                    "knowledge_record_id": item["knowledge_record_id"],
                    "score": item["score"],
                    "vector_score": item.get("vector_score"),
                    "rerank_score": item.get("rerank_score"),
                    "collection_member": item["collection_member"],
                    "source": item["source"],
                }
                for item in retrieval["results"]
            ],
        }
