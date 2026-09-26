"""Article tags repository: tag lookup and replacement."""

from app.features.articles.crud.repository import ArticleRepository
from app.features.shared.tags.mixins import TagLookupMixin, TagsReplaceMixin
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_model import Article


class ArticleTagsRepository(TagsReplaceMixin, TagLookupMixin, ArticleRepository):
    """Article repository extended with tag management."""

    _tags_association_table = article_tags
    _tags_entity_column = "article_id"
    _tags_entity_model = Article
