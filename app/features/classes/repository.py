"""Class repository: base CRUD plus abilities/throws/skills/spell-slot/subclass management."""

from sqlalchemy.orm import Session, selectinload

from app.core.base_repository import BaseRepository
from app.models import Character, Class, ClassPrimaryAbility, ClassSavingThrow, ClassSpellSlotProgression, Skill
from app.models.feature_model import Feature
from app.models.subclass_model import Subclass


class ClassRepository(BaseRepository[Class]):
    """Class-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: Session):
        super().__init__(
            Class,
            db,
            default_load_options=[
                selectinload(Class.available_skills),
                selectinload(Class.primary_abilities),
                selectinload(Class.saving_throws),
                selectinload(Class.spell_slot_progression),
                selectinload(Class.features),
                selectinload(Class.subclasses).selectinload(Subclass.features),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def is_in_use(self, class_id: int) -> bool:
        """
        Check whether the class is currently assigned to any character
        (characters.class_id), which would block deletion at the DB level
        via ON DELETE RESTRICT.
        """
        return self.db.query(Character).filter(Character.class_id == class_id).first() is not None

    def get_spell_slot_progression(self, class_id: int, class_level: int) -> dict[str, int]:
        """
        Return ``{spell_level: slots}`` for a single ``(class_id, class_level)`` pair.

        Only levels with an explicit ``ClassSpellSlotProgression`` row are
        included — a non-caster class (or a caster with no row for this
        level) simply returns ``{}``. Used by
        ``CharacterService`` to apply/refresh a character's actual spell
        slot totals whenever their level or class changes.
        """
        rows = (
            self.db.query(ClassSpellSlotProgression)
            .filter(
                ClassSpellSlotProgression.class_id == class_id,
                ClassSpellSlotProgression.class_level == class_level,
            )
            .all()
        )
        return {row.spell_level: row.slots for row in rows}

    def set_spell_slots(
        self, character_class: Class, class_level: int, slots_by_spell_level: dict[str, int], *, commit: bool = True
    ) -> Class:
        """
        Replace spell slot rows for a single ``class_level``.
        Full replace: existing rows for this level are deleted first.
        """

        self.db.query(ClassSpellSlotProgression).filter(
            ClassSpellSlotProgression.class_id == character_class.id,
            ClassSpellSlotProgression.class_level == class_level,
        ).delete()

        for spell_level, slots in slots_by_spell_level.items():
            self.db.add(
                ClassSpellSlotProgression(
                    class_id=character_class.id,
                    class_level=class_level,
                    spell_level=spell_level,
                    slots=slots,
                )
            )

        if commit:
            self.db.commit()
            self.db.refresh(character_class)
        else:
            self.db.flush()

        return character_class

    def set_primary_abilities(self, character_class: Class, abilities: list[str], *, commit: bool = True) -> Class:
        """
        Replace all primary abilities for a class with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a class + its primary abilities + its saving throws
        together) defer the commit and flush instead, without duplicating
        this method.
        """
        self.db.query(ClassPrimaryAbility).filter(ClassPrimaryAbility.class_id == character_class.id).delete()

        for ability in abilities:
            self.db.add(ClassPrimaryAbility(class_id=character_class.id, ability=ability))

        if commit:
            self.db.commit()
            self.db.refresh(character_class)
        else:
            self.db.flush()

        return character_class

    def set_saving_throws(self, character_class: Class, abilities: list[str], *, commit: bool = True) -> Class:
        """
        Replace all saving throw proficiencies for a class with the given list.

        See ``set_primary_abilities`` for the meaning of ``commit=False``.
        """
        self.db.query(ClassSavingThrow).filter(ClassSavingThrow.class_id == character_class.id).delete()

        for ability in abilities:
            self.db.add(ClassSavingThrow(class_id=character_class.id, ability=ability))

        if commit:
            self.db.commit()
            self.db.refresh(character_class)
        else:
            self.db.flush()

        return character_class

    def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""

        if not skill_ids:
            return []

        return self.db.query(Skill).filter(Skill.id.in_(skill_ids)).all()

    def set_available_skills(self, character_class: Class, skills: list[Skill], *, commit: bool = True) -> Class:
        """
        Replace all skills a class may choose proficiencies from.

        See ``set_primary_abilities`` for the meaning of ``commit=False``.
        """

        character_class.available_skills = skills

        if commit:
            self.db.commit()
            self.db.refresh(character_class)
        else:
            self.db.flush()

        return character_class

    def create_subclass(self, character_class: Class, payload: dict, *, commit: bool = True) -> Subclass:
        """
        Insert a ``Subclass`` row linked to ``character_class``.
        ``commit=False`` leaves the transaction open for the caller.
        """

        subclass = Subclass(**payload, class_id=character_class.id)
        self.db.add(subclass)
        if commit:
            self.db.commit()
            self.db.refresh(subclass)
        else:
            self.db.flush()
        return subclass

    def get_subclass(self, class_id: int, subclass_id: int) -> Subclass | None:
        """Fetch a subclass that belongs to ``class_id``, or ``None``."""

        return (
            self.db.query(Subclass)
            .options(selectinload(Subclass.features))
            .filter(Subclass.id == subclass_id, Subclass.class_id == class_id)
            .first()
        )

    def list_subclasses(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id`` ordered by name."""

        return (
            self.db.query(Subclass)
            .options(selectinload(Subclass.features))
            .filter(Subclass.class_id == class_id)
            .order_by(Subclass.name)
            .all()
        )

    def update_subclass(self, subclass: Subclass, fields: dict, *, commit: bool = True) -> Subclass:
        """Apply ``fields`` onto ``subclass`` and commit."""

        for field, value in fields.items():
            if hasattr(subclass, field):
                setattr(subclass, field, value)

        if commit:
            self.db.commit()
            self.db.refresh(subclass)
        else:
            self.db.flush()

        return subclass

    def delete_subclass(self, subclass: Subclass) -> None:
        """Delete a subclass (cascades to its features via ON DELETE CASCADE)."""

        self.db.delete(subclass)
        self.db.commit()

    def get_progression_features(self, class_id: int) -> list[Feature]:
        """
        Return all CLASS and SUBCLASS features for ``class_id``, ordered by level.
        Used to build the progression table in the service.
        """

        return (
            self.db.query(Feature)
            .filter(
                (Feature.class_id == class_id)
                | (Feature.subclass_id.in_(self.db.query(Subclass.id).filter(Subclass.class_id == class_id)))
            )
            .order_by(Feature.level, Feature.id)
            .all()
        )
