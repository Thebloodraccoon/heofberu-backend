"""Race CRUD service including ability-bonus and skill management."""

from typing import Any

from sqlalchemy.orm import Session

from app.constants import FeatureSourceType
from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.features.schemas import FeaturesReplace
from app.features.features.service import create_features_for_source, replace_features_for_source
from app.features.races.repository import RaceRepository
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
)
from app.models.race_model import Race


class RaceService(BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse]):
    """
    Race-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``name`` before create/update;
      - free-text ``search`` on the race name (via the inherited ``search``
        parameter, pinned by ``RaceRepository``'s ``search_fields``) and
        exact-match ``size`` filtering;
      - management of ability bonuses and granted skills, which live in
        their own association tables and have no generic base-class
        equivalent. ``create_race`` sets them up front, in the same
        transaction as the race itself, via ``BaseService._atomic()``;
      - a delete guard that blocks removing a race still assigned to any
        character (``characters.race_id`` is ``ON DELETE SET NULL`` at the
        DB level, so the guard is what prevents detachment).

    ``get_by_id``, ``get_all``, and ``delete`` are all inherited unchanged
    from ``BaseService`` — the in-use delete guard lives in
    ``BaseRepository.delete`` (via ``check_in_use_on_delete=True`` +
    ``RaceRepository.is_in_use``). Listing and detail reads are cached via
    ``@use_cache``; the lightweight listing derives its columns from
    ``RaceGetAllResponse``'s field names (id, name, size, is_homebrew) and
    is ordered by ``Race.id``. Because a race's writes also touch the
    ``features`` table (RACE-source rows), the service invalidates both its
    own namespace and ``features``.
    """

    repository: RaceRepository

    cache_namespaces = ("races", "features")

    def __init__(self, db: Session):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )

    @use_cache()
    def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[RaceGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    def get_by_id(self, item_id: int) -> RaceResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return super().get_by_id(item_id)

    def create_race(self, race_data: RaceCreate, created_by_id: int | None = None) -> RaceResponse:
        """
        Create a race after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it (relevant mainly
        for homebrew races) and is not part of ``RaceCreate`` itself, since
        it comes from the authenticated user, not client input.

        ``race_data.ability_bonuses`` / ``race_data.granted_skills`` /
        ``race_data.features`` are optional. If supplied, they're set in
        the *same transaction* as the race itself (base fields + bonuses +
        skills + features all commit together, or none do) via
        ``BaseService._atomic()`` — this is what lets a client create a
        fully-formed race in one request instead of one POST plus extra
        PUTs. Nested features are created through
        ``create_features_for_source`` with ``source_type=RACE``.

        Every write inside ``_atomic()`` passes ``commit=False`` —
        including ``repository.create`` itself — per the hazard documented
        on ``_atomic()``/``BaseRepository.create``.
        """

        skills = (
            self.resolve_ids(self.repository.get_skills_by_ids, race_data.granted_skills, "Skills")
            if race_data.granted_skills
            else None
        )

        payload = race_data.model_dump(exclude={"ability_bonuses", "granted_skills", "features"})
        payload["created_by_id"] = created_by_id

        with self._atomic():
            item = self.repository.create(payload, commit=False)

            if race_data.ability_bonuses:
                bonuses = [{"ability": b.ability, "bonus": b.bonus} for b in race_data.ability_bonuses]
                self.repository.set_ability_bonuses(item, bonuses, commit=False)

            if skills:
                self.repository.set_skills(item, skills, commit=False)

            create_features_for_source(
                self.repository.db,
                FeatureSourceType.RACE,
                item.id,
                race_data.features,
                created_by_id,
                commit=False,
            )

        self.repository.refresh(item)
        self._invalidate_cache()

        return self.response_schema.model_validate(item)

    def set_ability_bonuses(self, race_id: int, data: AbilityBonusesUpdate) -> RaceResponse:
        """Fully replace a race's ability score bonuses."""

        race = self._get_or_404(race_id)

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        updated_race = self.repository.set_ability_bonuses(race, bonuses)
        self._invalidate_cache()

        return self.response_schema.model_validate(updated_race)

    def set_skills(self, race_id: int, data: SkillsUpdate) -> RaceResponse:
        """Fully replace the skills granted by a race."""

        race = self._get_or_404(race_id)
        skills = self.resolve_ids(self.repository.get_skills_by_ids, data.skill_ids, "Skills")

        updated_race = self.repository.set_skills(race, skills)
        self._invalidate_cache()

        return self.response_schema.model_validate(updated_race)

    def replace_race_features(
        self, race_id: int, data: FeaturesReplace, created_by_id: int | None = None
    ) -> RaceResponse:
        """
        Full-replace a race's RACE-source features, matched by feature id.

        Items carrying an ``id`` update that feature in place — the id is
        kept, so character grants and any player notes on them survive.
        Items without an ``id`` create new features; existing features
        whose id is absent from the payload are deleted, cascading their
        grants away. Runs atomically, then reconciles the grants of every
        character of this race so their builds match the new feature set.
        """

        race = self._get_or_404(race_id)
        with self._atomic():
            replace_features_for_source(
                self.repository.db,
                FeatureSourceType.RACE,
                race.id,
                data.features,
                created_by_id,
                commit=False,
            )
            reconcile_characters_for_source(self.repository.db, FeatureSourceType.RACE, race.id)

        self.repository.refresh(race)
        self._invalidate_cache()

        return self.response_schema.model_validate(race)
