"""Git-like hash of an article version, chained to the previous version's hash: a rewritten history shows."""

import hashlib
import json
from typing import Any


def revision_hash(parent_hash: str | None, version: int, content: dict[str, Any]) -> str:
    """
    SHA-256 (hex) of ``version``, the previous version's hash and the content fields.

    Enum values are hashed by value (``"public"``); key order doesn't matter. Who edited/reviewed is not hashed:
    those FKs go ``NULL`` when a user is deleted, which must not break the chain.
    """

    payload = {key: getattr(value, "value", value) for key, value in content.items()}
    payload |= {"parent": parent_hash, "version": version}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
