"""Article cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

ARTICLE_CACHE_NAMESPACES = ("articles",)


async def invalidate_article_cache() -> None:
    """Purge every cache namespace an article read can hit."""

    for namespace in ARTICLE_CACHE_NAMESPACES:
        await invalidate(namespace)
