from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from ..application import DataForge
from ..errors import AuthenticationError
from .schemas import (
    AIApplicationChatRequest,
    AIApplicationCredentialRequest,
    AIApplicationInvokeRequest,
    AIApplicationRequest,
    AIApplicationVersionRequest,
)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("缺少 Authorization: Bearer <application-api-key>")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization 必须使用 Bearer 调用密钥")
    return token.strip()


def _sse(events: Iterator[dict]) -> StreamingResponse:
    def encode():
        for item in events:
            yield (
                f"event: {item['event']}\n"
                f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        encode(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def build_applications_router(dataforge: DataForge) -> APIRouter:
    router = APIRouter()
    control = APIRouter(prefix="/api", tags=["ai-applications"])
    serving = APIRouter(prefix="/v1/apps", tags=["application-serving"])
    configuration = APIRouter(
        prefix="/v1/application-configs", tags=["application-configuration"]
    )
    repository = dataforge.applications.repository

    @control.get("/ai-applications")
    def list_applications():
        return repository.list_applications()

    @control.post("/ai-applications", status_code=201)
    def create_application(payload: AIApplicationRequest):
        return dataforge.applications.create_application(
            payload.app_key, payload.name, payload.description
        )

    @control.get("/ai-applications/{application_id}")
    def get_application(application_id: str):
        application = repository.get_application(application_id)
        return {
            "application": application,
            "versions": repository.list_versions(application["id"]),
            "runs": repository.list_runs(application["id"], 20),
            "credentials": repository.list_credentials(application["id"]),
        }

    @control.post("/ai-applications/{application_id}/versions", status_code=201)
    def create_application_version(
        application_id: str, payload: AIApplicationVersionRequest
    ):
        return dataforge.applications.create_version(
            application_id,
            payload.application_binding_id,
            payload.llm_service_id,
            payload.config,
        )

    @control.get("/ai-application-versions")
    def list_application_versions(application_id: str | None = None):
        return repository.list_versions(application_id)

    @control.get("/ai-application-versions/{version_id}")
    def get_application_version(version_id: str):
        return repository.get_version(version_id)

    @control.post("/ai-application-versions/{version_id}/publish")
    def publish_application_version(version_id: str):
        return dataforge.applications.publish_version(version_id)

    @control.post("/ai-application-versions/{version_id}/preview")
    def preview_application_version(
        version_id: str, payload: AIApplicationInvokeRequest
    ):
        return dataforge.applications.preview_version(
            version_id,
            payload.inputs,
            history=payload.history,
            filters=payload.filters,
        )

    @control.post("/ai-applications/{application_id}/credentials", status_code=201)
    def create_application_credential(
        application_id: str, payload: AIApplicationCredentialRequest
    ):
        return dataforge.applications.create_credential(application_id, payload.name)

    @control.get("/ai-applications/{application_id}/credentials")
    def list_application_credentials(application_id: str):
        return repository.list_credentials(application_id)

    @control.post("/ai-application-credentials/{credential_id}/revoke")
    def revoke_application_credential(credential_id: str):
        return dataforge.applications.revoke_credential(credential_id)

    @control.get("/ai-application-runs")
    def list_application_runs(application_id: str | None = None, limit: int = 50):
        return repository.list_runs(application_id, min(200, max(1, limit)))

    @control.get("/ai-application-runs/{run_id}")
    def get_application_run(run_id: str):
        return repository.get_run(run_id)

    @control.post("/ai-applications/{app_key}/chat")
    def chat(app_key: str, payload: AIApplicationChatRequest):
        return dataforge.applications.chat(
            app_key,
            payload.message,
            history=payload.history,
            filters=payload.filters,
            top_k=payload.top_k,
        )

    def invoke_application(
        app_key: str,
        payload: AIApplicationInvokeRequest,
        authorization: str | None,
        version_number: int | None = None,
    ):
        token = _bearer_token(authorization)
        common = {
            "version_number": version_number,
            "history": payload.history,
            "filters": payload.filters,
            "session_id": payload.session_id,
            "user_id": payload.user_id,
            "metadata": payload.metadata,
        }
        if payload.stream:
            return _sse(
                dataforge.applications.invoke_stream(
                    app_key, token, payload.inputs, **common
                )
            )
        return dataforge.applications.invoke(app_key, token, payload.inputs, **common)

    @serving.post("/{app_key}/invoke")
    def invoke_current_application(
        app_key: str,
        payload: AIApplicationInvokeRequest,
        authorization: str | None = Header(default=None),
    ):
        return invoke_application(app_key, payload, authorization)

    @serving.post("/{app_key}/versions/{version_number}/invoke")
    def invoke_pinned_application(
        app_key: str,
        version_number: int,
        payload: AIApplicationInvokeRequest,
        authorization: str | None = Header(default=None),
    ):
        return invoke_application(app_key, payload, authorization, version_number)

    @configuration.get("/{app_key}")
    def get_current_application_config(app_key: str):
        return dataforge.applications.published_config(app_key)

    @configuration.get("/{app_key}/versions/{version_number}")
    def get_pinned_application_config(app_key: str, version_number: int):
        return dataforge.applications.published_config(app_key, version_number)

    router.include_router(control)
    router.include_router(serving)
    router.include_router(configuration)
    return router
