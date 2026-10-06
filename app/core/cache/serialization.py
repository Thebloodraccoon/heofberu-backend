"""
Pydantic-aware JSON (de)serialization for cached values.

``Page[...]`` and model instances are encoded with ``model_dump_json``
and decoded back through ``model_validate_json`` (enums, UUIDs and nested
models round-trip cleanly). A bare ``list[Model]`` schema (used by
``NestedCollectionService.list_for_source``) is decoded through a
``TypeAdapter`` instead, since a subscripted generic alias like
``list[Model]`` has no ``model_validate_json`` of its own — only the
``Model`` inside it does. Plain scalars go through ``json`` directly.
"""

import json
import typing
from typing import Any

from pydantic import BaseModel, TypeAdapter


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

    if schema is not None and typing.get_origin(schema) is list:
        return TypeAdapter(schema).validate_json(raw)

    return json.loads(raw)
