"""Subrace tags repository: tag lookup and replacement."""

from app.features.shared.tags.mixins import TagLookupMixin, TagsReplaceMixin
from app.features.subraces.crud.repository import SubraceRepository
from app.models.races.subrace_association_models import subrace_tags
from app.models.races.subrace_model import Subrace


class SubraceTagsRepository(TagsReplaceMixin, TagLookupMixin, SubraceRepository):
    """Subrace repository extended with tag management."""

    _tags_association_table = subrace_tags
    _tags_entity_column = "subrace_id"
    _tags_entity_model = Subrace
