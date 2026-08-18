from __future__ import annotations

import re
from typing import Any

from ..errors import ValidationError


SUPPORTED_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
VARIABLE = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_.-]*)\s*}}")

DEFAULT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "title": "用户问题",
            "description": "用于知识检索和回答生成的问题",
            "minLength": 1,
        }
    },
    "required": ["query"],
    "additionalProperties": True,
}

DEFAULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string", "title": "生成结果"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def normalize_contract(config: dict[str, Any]) -> dict[str, Any]:
    input_schema = config.get("input_schema") or DEFAULT_INPUT_SCHEMA
    output_schema = config.get("output_schema") or DEFAULT_OUTPUT_SCHEMA
    validate_schema(input_schema, "输入 Schema")
    validate_schema(output_schema, "输出 Schema")
    if input_schema.get("type") != "object" or output_schema.get("type") != "object":
        raise ValidationError("应用输入和输出 Schema 的根节点必须是 object")
    output_properties = output_schema.get("properties", {})
    if output_properties.get("answer", {}).get("type") != "string":
        raise ValidationError("当前文本生成运行时要求输出 Schema 声明 string 类型的 answer")
    unsupported_required = sorted(set(output_schema.get("required", [])) - {"answer"})
    if unsupported_required:
        raise ValidationError(
            f"当前文本生成运行时无法生成额外必填输出：{', '.join(unsupported_required)}"
        )

    query_field = str(config.get("query_field") or "query").strip()
    if not query_field:
        raise ValidationError("检索问题字段不能为空")
    query_schema = schema_at_path(input_schema, query_field)
    if not query_schema:
        raise ValidationError(f"输入 Schema 未声明检索问题字段：{query_field}")
    if query_schema.get("type") != "string":
        raise ValidationError("检索问题字段必须是 string")

    raw_mapping = config.get("prompt_variables") or {"question": query_field}
    if not isinstance(raw_mapping, dict) or not raw_mapping:
        raise ValidationError("Prompt 变量映射不能为空")
    mapping: dict[str, str] = {}
    for name, path in raw_mapping.items():
        variable = str(name).strip()
        input_path = str(path).strip()
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", variable):
            raise ValidationError(f"Prompt 变量名不合法：{variable}")
        if not schema_at_path(input_schema, input_path):
            raise ValidationError(f"Prompt 变量 {variable} 指向未声明字段：{input_path}")
        mapping[variable] = input_path

    allowed_filters = config.get("allowed_filter_fields") or []
    if not isinstance(allowed_filters, list) or any(not isinstance(item, str) for item in allowed_filters):
        raise ValidationError("运行时过滤字段必须是字符串数组")
    return {
        "input_schema": input_schema,
        "output_schema": output_schema,
        "query_field": query_field,
        "prompt_variables": mapping,
        "allowed_filter_fields": sorted({item.strip() for item in allowed_filters if item.strip()}),
        "include_citations": bool(config.get("include_citations", True)),
    }


def validate_schema(schema: Any, label: str = "Schema", path: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ValidationError(f"{label} {path} 必须是对象")
    kind = schema.get("type")
    if kind not in SUPPORTED_TYPES:
        raise ValidationError(f"{label} {path} 使用了不支持的类型：{kind}")
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise ValidationError(f"{label} {path}.enum 必须是数组")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValidationError(f"{label} {path} 的 properties/required 格式不正确")
        unknown = [name for name in required if name not in properties]
        if unknown:
            raise ValidationError(f"{label} {path} 的必填字段未声明：{', '.join(unknown)}")
        for name, child in properties.items():
            validate_schema(child, label, f"{path}.{name}")
    if kind == "array":
        if "items" not in schema:
            raise ValidationError(f"{label} {path} 的 array 必须声明 items")
        validate_schema(schema["items"], label, f"{path}[]")


def validate_instance(value: Any, schema: dict[str, Any], label: str = "inputs", path: str = "$") -> None:
    kind = schema["type"]
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[kind]
    if not valid:
        raise ValidationError(f"{label} {path} 应为 {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{label} {path} 不在允许值范围内")
    if kind == "object":
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise ValidationError(f"{label} 缺少必填字段：{path}.{name}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValidationError(f"{label} 包含未声明字段：{', '.join(unknown)}")
        for name, child in properties.items():
            if name in value:
                validate_instance(value[name], child, label, f"{path}.{name}")
    elif kind == "array":
        for index, item in enumerate(value):
            validate_instance(item, schema["items"], label, f"{path}[{index}]")
    elif kind == "string":
        if len(value) < int(schema.get("minLength", 0)):
            raise ValidationError(f"{label} {path} 长度不足")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValidationError(f"{label} {path} 超出最大长度")
    elif kind in {"number", "integer"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{label} {path} 小于最小值")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{label} {path} 超出最大值")


def value_at_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValidationError(f"输入中找不到字段：{path}")
        current = current[part]
    return current


def schema_at_path(schema: dict[str, Any], path: str) -> dict[str, Any] | None:
    current: Any = schema
    for part in path.split("."):
        if not isinstance(current, dict) or current.get("type") != "object":
            return None
        current = current.get("properties", {}).get(part)
        if current is None:
            return None
    return current


def template_variables(*templates: str) -> set[str]:
    return {match.group(1) for template in templates for match in VARIABLE.finditer(template)}


def render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(variables.get(name, match.group(0)))

    return VARIABLE.sub(replace, template)
