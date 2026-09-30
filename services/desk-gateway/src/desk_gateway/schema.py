"""Validation of tool arguments against the JSON Schema subset the contracts use.

The rosters only use: type (object/string/integer/number/boolean/array), required,
additionalProperties, enum, pattern, minLength/maxLength, minimum/maximum/exclusiveMinimum,
minItems/maxItems, items, default, format (ignored). Defaults are applied to the returned copy.
"""

from __future__ import annotations

import re
from typing import Any


class SchemaError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path or '$'}: {message}")
        self.path = path
        self.message = message


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def validate(schema: dict[str, Any], value: Any, path: str = "") -> Any:
    expected = schema.get("type")
    if expected and not _type_ok(value, expected):
        raise SchemaError(path, f"expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(path, f"must be one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaError(path, f"shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaError(path, f"longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise SchemaError(path, "does not match the required pattern")
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(path, f"below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(path, f"above {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise SchemaError(path, f"must be greater than {schema['exclusiveMinimum']}")
        return value
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(path, f"fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaError(path, f"more than {schema['maxItems']} items")
        item_schema = schema.get("items")
        if item_schema:
            return [validate(item_schema, v, f"{path}[{i}]") for i, v in enumerate(value)]
        return value
    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties") or {}
        out: dict[str, Any] = {}
        for key in schema.get("required") or []:
            if key not in value:
                raise SchemaError(f"{path}.{key}" if path else key, "is required")
        for key, item in value.items():
            if key in props:
                out[key] = validate(props[key], item, f"{path}.{key}" if path else key)
            elif schema.get("additionalProperties") is False:
                raise SchemaError(f"{path}.{key}" if path else key, "is not an accepted argument")
            else:
                out[key] = item
        for key, prop in props.items():
            if key not in out and "default" in prop:
                out[key] = prop["default"]
        return out
    return value
