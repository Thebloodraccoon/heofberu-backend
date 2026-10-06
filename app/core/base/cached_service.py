"""
Cached reference-service base: transparently cached listing/detail reads.

Reference catalog services (races, classes, backgrounds, feats, skills,
spells, items, features) used to re-declare the same two ``@use_cache``
decorated ``get_all``/``get_by_id`` overrides by hand. :class:`CachedService`
provides them once: the deserialization schema is resolved at call time from
the concrete subclass (``get_all_schema`` for listings, wrapped in ``Page``;
``response_schema`` for detail reads) by ``use_cache``'s dynamic-schema path,
so a subclass only declares ``cache_namespaces``.
"""

from typing import Any

from app.core.base.repository import ModelType
from app.core.base.service import (
    BaseService,
    CreateSchema,
    GetAllSchema,
    Page,
    ResponseSchema,
    UpdateSchema,
)
from app.core.cache import use_cache


class CachedService(BaseService[ModelType, CreateSchema, UpdateSchema, ResponseSchema, GetAllSchema]):
    """
    A :class:`BaseService` whose ``get_all``/``get_by_id`` are cached
    transparently via ``@use_cache``.

    The return annotations reference the service-level ``TypeVar``s, so
    ``use_cache`` falls back to resolving the schema per-call from the
    concrete instance (``get_all_schema`` / ``response_schema``) instead of
    at decoration time. Subclasses only set ``cache_namespaces``; the cache
    keys themselves are unchanged from the per-service overrides this
    replaces.
    """

    cache_namespaces: tuple[str, ...] = ()

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[GetAllSchema]:
        """Cached listing — see ``BaseService.get_all``."""

        return await super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    async def get_by_id(self, item_id: int) -> ResponseSchema:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return await super().get_by_id(item_id)
