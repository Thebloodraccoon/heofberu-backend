"""Article tags repository: tag lookup and replacement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.articles.base import ArticleScopedRepository
from app.features.shared.tags.mixins import TagLookupMixin, TagsReplaceMixin
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_model import Article


class ArticleTagsRepository(TagsReplaceMixin, TagLookupMixin, ArticleScopedRepository):
    """Article lookups plus tag management; loads tags and images because the service returns the full article."""

    _tags_association_table = article_tags
    _tags_entity_column = "article_id"
    _tags_entity_model = Article

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` with tags and images eager-loaded."""

        super().__init__(db, load_tags_and_images=True)
