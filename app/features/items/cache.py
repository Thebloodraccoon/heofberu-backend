"""Item cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# Classes/backgrounds embed ItemBriefResponse rows and nest item listings.
ITEM_CACHE_NAMESPACES = ("items", "nested_items", "classes", "backgrounds")


async def invalidate_item_cache() -> None:
    """Purge every cache namespace an item read can hit."""

    for namespace in ITEM_CACHE_NAMESPACES:
        await invalidate(namespace)
