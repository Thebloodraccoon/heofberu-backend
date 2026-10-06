"""Article cache coordination: exact-key invalidation for single-article writes, a namespace purge for the rest."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import build_cache_key

ARTICLE_TREE_NAMESPACE = "article_trees"
ARTICLE_CACHE_NAMESPACES = ("articles", ARTICLE_TREE_NAMESPACE)
"""
``articles``: one detail payload per article (point-invalidated, ``article_cache_key``).
``article_trees``: children/ancestors/descendants/relations lists, which embed other articles' titles and
visibility, so an article write touching ``TREE_PAYLOAD_FIELDS`` (or its status / existence) purges the whole
namespace; a relation write drops only its two ends' relation lists (``relations.service.invalidate_relations``).
"""


TREE_PAYLOAD_FIELDS = frozenset({"title", "article_type", "subtype_id", "visibility", "parent_id"})
"""Article fields the ``article_trees`` lists depend on (``ArticleBrief`` + visibility filter + position; a slug
only changes with the title). An edit touching none of them (body/excerpt) leaves the namespace warm."""


def article_cache_key(article_id: int) -> str:
    """Exact key under which ``ArticleCrudService.get_by_id`` caches one article."""

    # Same name and signature as the decorated ``ArticleCrudService.get_by_id`` (not imported: it imports this module).
    return build_cache_key(BaseService.get_by_id, None, article_id, namespace=ARTICLE_CACHE_NAMESPACES[0])


async def invalidate_articles(db: AsyncSession, *article_ids: int) -> None:
    """Drop these articles' cached payloads once the surrounding transaction commits (at once outside one)."""

    await invalidate_after_commit(db, keys=[article_cache_key(article_id) for article_id in article_ids])


async def invalidate_all_articles(db: AsyncSession) -> None:
    """Drop every cached article payload after commit: for writes that stale many of them (subtype/tag rename)."""

    await invalidate_after_commit(db, *ARTICLE_CACHE_NAMESPACES)


async def invalidate_article_trees(db: AsyncSession) -> None:
    """Drop the cached tree and relation lists after commit (any article or relation write can stale them)."""

    await invalidate_after_commit(db, ARTICLE_TREE_NAMESPACE)
