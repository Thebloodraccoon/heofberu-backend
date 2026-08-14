"""Item cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

ITEM_CACHE_NAMESPACES = ("items",)


async def invalidate_item_cache() -> None:
    """
    Purge every cache namespace an item read can hit.

    ``GET /items`` (``items`` namespace) is served from cache. Any write
    to an item — catalog CRUD via ``/items`` or a class/background
    starting-equipment list referencing it — must call this after its
    transaction commits. The class/background catalogs already include
    ``"items"`` in their ``cache_namespaces`` for the same reason.
    """
    for namespace in ITEM_CACHE_NAMESPACES:
        await invalidate(namespace)
