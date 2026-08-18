from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ValidationError


FIELD_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*}}")


def resolve_field(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_template(
    template: str,
    payload: dict[str, Any],
    *,
    missing_policy: str = "empty",
) -> str:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        field = match.group(1)
        value = resolve_field(payload, field)
        if value is None:
            missing.append(field)
            return ""
        return stringify(value)

    rendered = FIELD_PATTERN.sub(replace, template)
    if missing and missing_policy == "error":
        raise ValidationError(f"模板字段缺失：{'、'.join(sorted(set(missing)))}")
    return rendered.strip()


def referenced_fields(template: str) -> list[str]:
    return list(dict.fromkeys(FIELD_PATTERN.findall(template)))


def build_projection(
    record: dict[str, Any],
    locator: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    source = {**record, "source_locator": locator}
    indexed_text = render_template(
        str(config.get("embedding_template") or ""),
        source,
        missing_policy=str(config.get("missing_policy") or "error"),
    )
    if not indexed_text:
        raise ValidationError("向量化模板生成了空文本")

    stored: dict[str, Any] = {}
    for field in config.get("stored_fields") or []:
        stored[field] = resolve_field(source, field)

    metadata: dict[str, Any] = {}
    for field in config.get("metadata_fields") or []:
        metadata[field] = resolve_field(source, field)

    filters: dict[str, Any] = {}
    for mapping in config.get("filter_fields") or []:
        source_name = str(mapping.get("source") or "").strip()
        target_name = str(mapping.get("target") or source_name).strip()
        value = resolve_field(source, source_name)
        if value is None:
            value = mapping.get("default")
        filters[target_name] = coerce_scalar(value, str(mapping.get("type") or "string"))

    metadata["stored"] = stored
    return indexed_text, metadata, filters


def coerce_scalar(value: Any, kind: str) -> Any:
    if value is None:
        return None
    try:
        if kind in {"integer", "int"}:
            return int(value)
        if kind in {"number", "float"}:
            return float(value)
        if kind in {"boolean", "bool"}:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "是"}
            return bool(value)
        return stringify(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"无法把值 {value!r} 转换为 {kind}") from exc
