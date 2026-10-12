"""Finite offline schema evaluator for the packaged portable contract dialect.

Unsupported schema keywords fail closed; no URI resolver or executable input.
"""
from __future__ import annotations

import json
import re
from typing import Any


class ContractError(ValueError):
    """Malformed, incomplete or unsupported portable proposal."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def load_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate JSON member")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError("nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError("invalid UTF-8 JSON") from error


def validate(value: Any, schema: dict[str, Any], path: str = "input") -> None:
    allowed = {"type", "const", "enum", "properties", "required", "additionalProperties",
               "items", "minItems", "maxItems", "minLength", "maxLength", "pattern",
               "minimum", "maximum", "description", "title", "$schema", "$id"}
    if set(schema) - allowed:
        raise ContractError("unsupported schema keyword")
    types = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str), "integer": lambda v: type(v) is int,
             "boolean": lambda v: type(v) is bool, "null": lambda v: v is None}
    kind = schema.get("type")
    if kind not in types or not types[kind](value):
        raise ContractError(f"{path}: invalid type")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ContractError(f"{path}: unsupported constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"{path}: unsupported selection")
    if kind == "object":
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            raise ContractError("object schema must be closed")
        if set(value) - set(props) or set(schema.get("required", [])) - set(value):
            raise ContractError(f"{path}: missing or unknown fields")
        for key, item in value.items():
            validate(item, props[key], f"{path}.{key}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            raise ContractError(f"{path}: invalid item count")
        for item in value:
            validate(item, schema["items"], path + "[]")
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 65536):
            raise ContractError(f"{path}: invalid length")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ContractError(f"{path}: invalid format")
    elif kind == "integer":
        if not schema.get("minimum", value) <= value <= schema.get("maximum", value):
            raise ContractError(f"{path}: outside bounds")
