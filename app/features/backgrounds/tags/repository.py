"""Background tags repository: tag lookup and replacement."""

from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.shared.tags.mixins import TagLookupMixin, TagsReplaceMixin
from app.models.backgrounds.background_association_models import background_tags
from app.models.backgrounds.background_model import Background


class BackgroundTagsRepository(TagsReplaceMixin, TagLookupMixin, BackgroundRepository):
    """Background repository extended with tag management."""

    _tags_association_table = background_tags
    _tags_entity_column = "background_id"
    _tags_entity_model = Background
