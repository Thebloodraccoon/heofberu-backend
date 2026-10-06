"""
Shared bounded id types: one definition of the PostgreSQL ``integer`` (int32) id range.

Payload/path/query ids are bounded so an oversized value is a 422 instead of a driver overflow (500).
"""

from typing import Annotated

from fastapi import Path
from pydantic import Field

INT32_MAX = 2_147_483_647

#: A database integer id in a request body.
EntityId = Annotated[int, Field(ge=1, le=INT32_MAX)]
#: The same bound for a path parameter.
EntityIdPath = Annotated[int, Path(ge=1, le=INT32_MAX)]
