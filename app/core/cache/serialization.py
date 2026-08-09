"""
Pydantic-aware JSON (de)serialization for cached values.

``Page[...]`` and model instances are encoded with ``model_dump_json``
and decoded back through ``model_validate_json`` (enums, UUIDs and nested
models round-trip cleanly). Plain scalars go through ``json`` directly.
"""

import json
from typing import Any

from pydantic import BaseModel


def encode(value: Any) -> str:
    """Serialize a cached value (model, ``Page``, list/tuple, scalar, ``None``) to JSON."""
    if value is None:
        return "null"

    if isinstance(value, BaseModel):
        return value.model_dump_json()

    if isinstance(value, list | tuple):
        return "[" + ",".join(encode(item) for item in value) + "]"

    return json.dumps(value, default=str)


def decode(raw: str, schema: Any = None) -> Any:
    """Deserialize a cached value, optionally back into a Pydantic model."""

    if raw == "null":
        return None

    if schema is not None and hasattr(schema, "model_validate_json"):
        return schema.model_validate_json(raw)

    return json.loads(raw)
