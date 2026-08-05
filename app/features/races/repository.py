"""Race repository: base CRUD plus ability-bonus/skill management."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models import Character
from app.models.race_association_models import RaceAbilityBonus
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceRepository(BaseRepository[Race]):
    """
    Race-specific repository built on :class:`BaseRepository`.

    ``ability_bonuses`` and ``granted_skills`` are always part of
    ``RaceResponse``, so they're wired up as ``default_load_options``
    rather than re-implemented here via a hand-rolled ``get_all`` override.

    ``search_fields=["name"]`` pins free-text ``search`` (on the inherited
    ``get_all``/``get_brief``) to just ``name`` — without this, the base
    class's auto-detection would also search ``traits`` (also a text
    column on ``Race``), which isn't the intended behavior here. ``size``
    stays available as an exact-match ``filters`` key, inherited unchanged.

    ``get_all`` and ``get_brief`` are *not* overridden here anymore: the
    base class's pagination + eager-loading (``default_load_options``) +
    exact-match ``filters`` + free-text ``search`` (``search_fields``)
    cover everything races need.
    """

    def __init__(self, db: Session):
        super().__init__(
            Race,
            db,
            default_load_options=[
                selectinload(Race.ability_bonuses),
                selectinload(Race.granted_skills),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def is_in_use(self, race_id: int) -> bool:
        """
        Check whether the race is currently assigned to any character
        (characters.race_id), which would block deletion at the DB level
        via ON DELETE RESTRICT.
        """
        return self.db.query(Character).filter(Character.race_id == race_id).first() is not None

    def set_ability_bonuses(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> Race:
        """
        Replace all ability bonuses for a race with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a race + its bonuses + its skills together) defer
        the commit and flush instead, without duplicating this method.
        """

        self.db.query(RaceAbilityBonus).filter(RaceAbilityBonus.race_id == race.id).delete()

        for item in bonuses:
            self.db.add(RaceAbilityBonus(race_id=race.id, ability=item["ability"], bonus=item["bonus"]))

        if commit:
            self.db.commit()
            self.db.refresh(race)
        else:
            self.db.flush()

        return race

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""
        if not skill_ids:
            return []

        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def set_skills(self, race: Race, skills: list[Skill], *, commit: bool = True) -> Race:
        """
        Replace all granted skills for a race with the given list.

        See ``set_ability_bonuses`` for the meaning of ``commit=False``.
        """

        race.granted_skills = skills

        if commit:
            self.db.commit()
            self.db.refresh(race)
        else:
            self.db.flush()

        return race
