from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models import CharacterAbilityScore
from app.models.character_association_models import (
    CharacterFeat,
    CharacterSavingThrowProficiency,
    CharacterSkillProficiency,
    CharacterSpellSlot,
)
from app.models.character_model import Character
from app.models.character_spell_model import CharacterSpell
from app.models.spell_model import Spell


class CharacterRepository(BaseRepository[Character]):
    """
    Shared repository for the ``Character`` model.

    Used by every character sub-domain service (core, proficiencies,
    spells, attacks, rolls) — not split further, since it operates on one
    model/table and one DB session regardless of which sub-domain is
    calling it.
    """

    def __init__(self, db: Session):
        super().__init__(Character, db)

    def get_all(self) -> list[Character]:
        """
        Get all characters, ordered by name. GM-only use case.

        Overrides base pagination-based get_all.
        """

        return self.db.query(Character).order_by(Character.name).all()

    def get_all_by_owner(self, owner_id: int) -> list[Character]:
        """Get characters owned by a specific user. Player use case."""

        return self.db.query(Character).filter(Character.owner_id == owner_id).order_by(Character.name).all()

    def create(self, character_data: dict, owner_id: int) -> Character:  # type: ignore[override]
        """Create a character for a given owner (overrides base create signature)."""

        character = Character(**character_data, owner_id=owner_id)
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)

        return character

    def update_hp(self, character: Character, current_hp: int, temp_hp: int) -> Character:
        """Set current and temp HP directly. Bounds/validation happen in the service."""

        character.current_hp = current_hp
        character.temp_hp = temp_hp
        self.db.commit()
        self.db.refresh(character)

        return character

    def get_skill_proficiency(self, character_id: int, skill_id: int) -> CharacterSkillProficiency | None:
        return (
            self.db.query(CharacterSkillProficiency)
            .filter(
                CharacterSkillProficiency.character_id == character_id,
                CharacterSkillProficiency.skill_id == skill_id,
            )
            .first()
        )

    def get_saving_throw_proficiency(self, character_id: int, ability: str) -> CharacterSavingThrowProficiency | None:
        return (
            self.db.query(CharacterSavingThrowProficiency)
            .filter(
                CharacterSavingThrowProficiency.character_id == character_id,
                CharacterSavingThrowProficiency.ability == ability,
            )
            .first()
        )

    def set_skill_proficiencies(self, character: Character, proficiencies: list[dict]) -> Character:
        """
        Replace all skill proficiencies for a character with the given list.

        Each item is expected to have 'skill_id' and 'is_expertise'.
        """
        self.db.query(CharacterSkillProficiency).filter(CharacterSkillProficiency.character_id == character.id).delete()

        for item in proficiencies:
            self.db.add(
                CharacterSkillProficiency(
                    character_id=character.id,
                    skill_id=item["skill_id"],
                    is_expertise=item.get("is_expertise", False),
                )
            )

        self.db.commit()
        self.db.refresh(character)
        return character

    def set_saving_throw_proficiencies(self, character: Character, abilities: list[str]) -> Character:
        """Replace all saving throw proficiencies for a character with the given list."""

        self.db.query(CharacterSavingThrowProficiency).filter(
            CharacterSavingThrowProficiency.character_id == character.id
        ).delete()

        for ability in abilities:
            self.db.add(CharacterSavingThrowProficiency(character_id=character.id, ability=ability))

        self.db.commit()
        self.db.refresh(character)
        return character

    def get_spell_slot(self, character_id: int, level: str) -> CharacterSpellSlot | None:
        return (
            self.db.query(CharacterSpellSlot)
            .filter(
                CharacterSpellSlot.character_id == character_id,
                CharacterSpellSlot.spell_level == level,
            )
            .first()
        )

    def upsert_spell_slot(
        self, character_id: int, level: str, total: int | None, used: int | None
    ) -> CharacterSpellSlot:
        """
        Create or update the spell slot entry for a given level.

        If the entry doesn't exist yet, it's created with the given values
        (defaulting missing fields to 0). Validation of the used<=total
        invariant happens in the service before this is called.
        """

        slot = self.get_spell_slot(character_id, level)
        if slot is None:
            slot = CharacterSpellSlot(
                character_id=character_id,
                spell_level=level,
                total=total if total is not None else 0,
                used=used if used is not None else 0,
            )
            self.db.add(slot)
        else:
            if total is not None:
                slot.total = total
            if used is not None:
                slot.used = used

        self.db.commit()
        self.db.refresh(slot)
        return slot

    def get_all_spell_slots(self, character_id: int) -> list[CharacterSpellSlot]:
        return self.db.query(CharacterSpellSlot).filter(CharacterSpellSlot.character_id == character_id).all()

    def apply_spell_slot_progression(self, character_id: int, slots_by_level: dict[str, int]) -> list[CharacterSpellSlot]:
        """
        Sync a character's actual ``CharacterSpellSlot.total`` values to
        match ``slots_by_level`` (as returned by
        ``ClassRepository.get_spell_slot_progression`` for the character's
        current class/level).

        For each level in ``slots_by_level``: upsert the slot row, setting
        ``total`` to the given value. ``used`` is left untouched unless it
        would exceed the new ``total``, in which case it's clamped down to
        ``total`` (so the ``used <= total`` invariant always holds — this
        can only ever reduce ``used``, never invent slots as "spent").

        For any level the character currently has a row for but that is
        *not* present in ``slots_by_level`` (e.g. leveling down, or
        switching to a class that doesn't grant that level): the row's
        ``total`` is set to 0 and ``used`` is clamped to 0 with it, rather
        than deleted — this keeps history/ordering stable and matches
        ``upsert_spell_slot``'s "0 total = no slots" convention elsewhere.

        Levels never granted and not currently present in the character's
        rows are left alone (no zero-row is created for them).
        """

        existing = {slot.spell_level: slot for slot in self.get_all_spell_slots(character_id)}

        for level, total in slots_by_level.items():
            slot = existing.get(level)
            if slot is None:
                self.db.add(
                    CharacterSpellSlot(
                        character_id=character_id,
                        spell_level=level,
                        total=total,
                        used=0,
                    )
                )
            else:
                slot.total = total
                if slot.used > total:
                    slot.used = total

        for level, slot in existing.items():
            if level not in slots_by_level:
                slot.total = 0
                slot.used = 0

        self.db.commit()
        return self.get_all_spell_slots(character_id)

    def reset_all_spell_slots(self, character_id: int) -> None:
        """Set used=0 for every spell slot entry of the character (long rest)."""

        self.db.query(CharacterSpellSlot).filter(CharacterSpellSlot.character_id == character_id).update(
            {CharacterSpellSlot.used: 0}
        )
        self.db.commit()

    def get_known_spells(self, character_id: int) -> list[CharacterSpell]:
        return self.db.query(CharacterSpell).filter(CharacterSpell.character_id == character_id).all()

    def get_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell | None:
        return (
            self.db.query(CharacterSpell)
            .filter(
                CharacterSpell.character_id == character_id,
                CharacterSpell.spell_id == spell_id,
            )
            .first()
        )

    def add_known_spell(self, character_id: int, spell_id: int) -> CharacterSpell:
        character_spell = CharacterSpell(character_id=character_id, spell_id=spell_id)
        self.db.add(character_spell)
        self.db.commit()
        self.db.refresh(character_spell)
        return character_spell

    def remove_known_spell(self, character_spell: CharacterSpell) -> bool:
        self.db.delete(character_spell)
        self.db.commit()
        return True

    def count_known_spells_at_level(self, character_id: int, level: str) -> int:
        """
        Count how many spells the character already knows at a given
        ``Spell.level`` — compared against ``CharacterSpellSlot.total``
        for that level to cap how many spells of that level can be known
        at once. See ``CharacterSpellService.add_known_spell``.
        """

        return (
            self.db.query(CharacterSpell)
            .join(Spell, Spell.id == CharacterSpell.spell_id)
            .filter(
                CharacterSpell.character_id == character_id,
                Spell.level == level,
            )
            .count()
        )

    def get_character_feats(self, character_id: int) -> list[CharacterFeat]:
        """Get every feat grant for a character."""

        return self.db.query(CharacterFeat).filter(CharacterFeat.character_id == character_id).all()

    def get_character_feat_by_id(self, character_id: int, character_feat_id: int) -> CharacterFeat | None:
        """Fetch a single feat grant by its own id, scoped to the character."""

        return (
            self.db.query(CharacterFeat)
            .filter(
                CharacterFeat.id == character_feat_id,
                CharacterFeat.character_id == character_id,
            )
            .first()
        )

    def get_character_feat_by_feat_id(self, character_id: int, feat_id: int) -> CharacterFeat | None:
        """Fetch a character's grant for a specific feat, if any (used for duplicate checks)."""

        return (
            self.db.query(CharacterFeat)
            .filter(
                CharacterFeat.character_id == character_id,
                CharacterFeat.feat_id == feat_id,
            )
            .first()
        )

    def add_character_feat(
        self, character_id: int, feat_id: int, ability_score_increase_id: int | None
    ) -> CharacterFeat:
        """Grant a feat to a character, with an optional ASI choice."""

        grant = CharacterFeat(
            character_id=character_id,
            feat_id=feat_id,
            ability_score_increase_id=ability_score_increase_id,
        )
        self.db.add(grant)
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def set_character_feat_ability_score_increase(
        self, grant: CharacterFeat, ability_score_increase_id: int | None
    ) -> CharacterFeat:
        """Set (or clear, if ``None``) the ASI choice on an existing feat grant."""

        grant.ability_score_increase_id = ability_score_increase_id
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def remove_character_feat(self, grant: CharacterFeat) -> bool:
        """Revoke a feat grant."""

        self.db.delete(grant)
        self.db.commit()
        return True

    def get_ability_score_cache(self, character_id: int) -> CharacterAbilityScore | None:
        """Fetch the cached effective-ability-score row, or None if never computed."""

        return (
            self.db.query(CharacterAbilityScore)
            .filter(CharacterAbilityScore.character_id == character_id)
            .first()
        )

    def upsert_ability_score_cache(self, character_id: int, totals: dict) -> CharacterAbilityScore:
        """
        Create or update the cached effective ability scores for a
        character. ``totals`` keys are ``strength_total``,
        ``dexterity_total``, ``constitution_total``,
        ``intelligence_total``, ``wisdom_total``, ``charisma_total``.
        """

        cache = self.get_ability_score_cache(character_id)
        if cache is None:
            cache = CharacterAbilityScore(character_id=character_id, **totals)
            self.db.add(cache)
        else:
            for field, value in totals.items():
                setattr(cache, field, value)

        self.db.commit()
        self.db.refresh(cache)
        return cache