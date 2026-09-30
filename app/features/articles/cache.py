"""Article cache coordination: a namespace-wide flush plus a point invalidation for single-row writes."""

from app.core.cache import invalidate
from app.core.cache.client import cache_delete_key, cache_prefix

ARTICLE_CACHE_NAMESPACES = ("articles",)


async def invalidate_article_cache() -> None:
    """Purge every cached article: for writes that can stale ANOTHER article's payload (delete, subtype/tag rename)."""

    for namespace in ARTICLE_CACHE_NAMESPACES:
        await invalidate(namespace)


async def invalidate_article(article_id: int) -> None:
    """Point-invalidate one article's cached ``get_by_id`` payload (key must match ``use_cache``'s ``_build_key``)."""

    await cache_delete_key(f"{cache_prefix()}:articles:get_by_id:1={article_id}")
