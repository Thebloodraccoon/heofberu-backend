"""Race tags repository: tag lookup and replacement."""

from app.features.races.crud.repository import RaceRepository
from app.features.shared.tags.mixins import TagLookupMixin, TagsReplaceMixin
from app.models.races.race_association_models import race_tags
from app.models.races.race_model import Race


class RaceTagsRepository(TagsReplaceMixin, TagLookupMixin, RaceRepository):
    """Race repository extended with tag management."""

    _tags_association_table = race_tags
    _tags_entity_column = "race_id"
    _tags_entity_model = Race
