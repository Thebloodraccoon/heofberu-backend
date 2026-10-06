"""Contract test: the exact invalidation key must equal the key ``@use_cache`` writes for ``get_by_id``."""

from types import SimpleNamespace

from app.core.cache import build_cache_key
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES, article_cache_key
from app.features.articles.crud.service import ArticleCrudService


def test_article_cache_key_matches_the_decorated_get_by_id_key():
    service = SimpleNamespace(cache_namespaces=ARTICLE_CACHE_NAMESPACES)

    assert article_cache_key(42) == build_cache_key(ArticleCrudService.get_by_id, service, 42)
    assert article_cache_key(42) == build_cache_key(ArticleCrudService.get_by_id, service, item_id=42)


def test_article_cache_key_is_in_the_articles_namespace():
    assert article_cache_key(7) == "cache:articles:get_by_id:1=7"
