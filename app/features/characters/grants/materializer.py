"""
Materializer: reconcile a character's effect rows against one feature grant's effect tree.

A grant's "desired" effect surface is the union of:
- the feature's fixed (``feature_id``-owned) effect rows, and
- the effect rows bundled inside the options the player picked for the
  grant's choice groups.

The materializer diffs that against the rows currently stored for the
grant (``source_character_feature_id == grant.id``) and writes the delta:
rows whose effect vanished are deleted (cascade keeps this targeted, never
touching rows owned by other grants or raw free-form rows), and missing
rows are inserted — deduped against the character's other rows so unique
constraints (skill PK, save/armor per-character uniques) never collide.
Skill ``is_expertise`` is monotonic: an existing GM-upgraded expertise row
survives a non-expertise effect re-materialization.

Never commits — the caller's transaction owns persistence.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_engine_models import (
    CharacterArmorProficiency,
    CharacterFeatureChoice,
    CharacterGrantedSpell,
    CharacterSavingThrowProficiency,
    CharacterWeaponProficiency,
)
from app.models.character_feature_model import CharacterFeature
from app.models.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
from app.models.feature_model import Feature


def engine_effect_loads() -> list:
    """Eager loads for the whole feature-engine effect tree (shared loader)."""

    option_effect_attrs = (
        "ability_effects",
        "skill_effects",
        "saving_throw_effects",
        "armor_effects",
        "weapon_effects",
        "spell_effects",
    )

    return [
        selectinload(Feature.ability_effects),
        selectinload(Feature.skill_effects),
        selectinload(Feature.saving_throw_effects),
        selectinload(Feature.armor_effects),
        selectinload(Feature.weapon_effects),
        selectinload(Feature.spell_effects),
    ] + [
        selectinload(Feature.choice_groups)
        .selectinload(FeatureChoiceGroup.options)
        .selectinload(getattr(FeatureChoiceOption, attr))
        for attr in option_effect_attrs
    ]


async def load_feature_effect_tree(db: AsyncSession, feature_id: int) -> Feature | None:
    """Fetch a feature with its full engine effect tree, or ``None`` if it doesn't exist."""

    result = await db.execute(
        select(Feature).where(Feature.id == feature_id).options(*engine_effect_loads())
    )
    return result.scalars().first()


@dataclass
class ResolvedOption:
    """One picked option inside a choice group, with the concrete skill/spell it resolved any open effect to."""

    option: FeatureChoiceOption
    skill_id: int | None = None
    spell_id: int | None = None


@dataclass
class DesiredEffects:
    """The effect-surface a grant *should* produce, ready to diff against the stored rows."""

    skills: dict[int, bool] = field(default_factory=dict)
    saving_throws: set = field(default_factory=set)
    armor: set = field(default_factory=set)
    weapons: list[tuple] = field(default_factory=list)
    spells: list[tuple] = field(default_factory=list)


class FeatureGrantMaterializer:
    """Reconciliation of one grant's effect rows to its feature's effect tree (no commits)."""

    async def build_desired(
        self,
        feature,
        choices: dict[int, list[ResolvedOption]],
    ) -> DesiredEffects:
        """
        Compose the grant's desired effect surface from the feature's fixed
        rows plus each chosen option's bundle.

        ``choices`` maps a choice-group id to its picked (and resolved)
        options; groups absent or under-filled simply contribute nothing.
        Ability effects are NOT materialized into character tables — they
        feed the ability-score calculator directly (see
        ``CharacterStatsRepository.get_feature_increases``) — so they are
        absent here by design.
        """

        desired = DesiredEffects()

        for effect in feature.skill_effects:
            if effect.skill_id is None:
                continue
            desired.skills[effect.skill_id] = desired.skills.get(effect.skill_id, False) or bool(
                effect.grants_expertise
            )

        for effect in feature.saving_throw_effects:
            desired.saving_throws.add(effect.ability)

        for effect in feature.armor_effects:
            desired.armor.add(effect.armor_type)

        for effect in feature.weapon_effects:
            if effect.weapon_category is None and effect.item_id is None:
                continue
            desired.weapons.append((effect.weapon_category, effect.item_id))

        # Fixed feature-level spell effects: only concrete ``spell_id`` grants
        # materialize here — an open (school+level-filtered) fixed effect has
        # no choice point to resolve it, so it is skipped (author open spells
        # inside choice options instead).
        for effect in feature.spell_effects:
            if effect.spell_id is None:
                continue
            desired.spells.append((effect.spell_id, effect.always_prepared, effect.counts_against_known_limit))

        for resolved in choices.values():
            for item in resolved:
                self._fold_option(item, desired)

        return desired

    def _fold_option(self, item: ResolvedOption, desired: DesiredEffects) -> None:
        """Fold one picked option's bundle into ``desired``."""

        option = item.option

        for effect in option.skill_effects:
            skill_id = effect.skill_id if effect.skill_id is not None else item.skill_id
            if skill_id is None:
                continue
            desired.skills[skill_id] = desired.skills.get(skill_id, False) or bool(effect.grants_expertise)

        for effect in option.saving_throw_effects:
            desired.saving_throws.add(effect.ability)

        for effect in option.armor_effects:
            desired.armor.add(effect.armor_type)

        for effect in option.weapon_effects:
            if effect.weapon_category is None and effect.item_id is None:
                continue
            desired.weapons.append((effect.weapon_category, effect.item_id))

        for effect in option.spell_effects:
            spell_id = effect.spell_id if effect.spell_id is not None else item.spell_id
            if spell_id is None:
                continue
            desired.spells.append((spell_id, effect.always_prepared, effect.counts_against_known_limit))

    async def reconcile(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        choices: dict[int, list[ResolvedOption]],
    ) -> None:
        """
        Make the character's effect rows match the grant's desired surface.

        Deletes this grant's rows whose effect no longer applies, inserts the
        missing ones (deduped across all of the character's rows), and
        preserves skill expertise upgrades. Never commits.
        """

        desired = await self.build_desired(feature, choices)
        await self._reconcile_skills(db, character_id, grant, desired)
        await self._reconcile_saves(db, character_id, grant, desired)
        await self._reconcile_armor(db, character_id, grant, desired)
        await self._reconcile_weapons(db, character_id, grant, desired)
        await self._reconcile_spells(db, character_id, grant, desired)

    async def _reconcile_skills(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile skill-proficiency rows (preserving expertise upgrades)."""

        result = await db.execute(
            select(CharacterSkillProficiency).where(CharacterSkillProficiency.character_id == character_id)
        )
        existing = list(result.scalars().unique().all())

        by_skill = {row.skill_id: row for row in existing}

        for row in existing:
            if row.source_character_feature_id == grant.id and row.skill_id not in desired.skills:
                await db.delete(row)

        for skill_id, wants_expertise in desired.skills.items():
            row = by_skill.get(skill_id)
            if row is not None:
                if row.source_character_feature_id == grant.id and wants_expertise and not row.is_expertise:
                    row.is_expertise = True
                continue

            db.add(
                CharacterSkillProficiency(
                    character_id=character_id,
                    skill_id=skill_id,
                    is_expertise=wants_expertise,
                    source_character_feature_id=grant.id,
                )
            )

    async def _reconcile_saves(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile saving-throw proficiency rows (per-character unique on ability)."""

        result = await db.execute(
            select(CharacterSavingThrowProficiency).where(
                CharacterSavingThrowProficiency.character_id == character_id
            )
        )
        existing = list(result.scalars().unique().all())
        present = {row.ability for row in existing}

        for row in existing:
            if row.source_character_feature_id == grant.id and row.ability not in desired.saving_throws:
                await db.delete(row)

        for ability in desired.saving_throws:
            if ability not in present:
                db.add(
                    CharacterSavingThrowProficiency(
                        character_id=character_id,
                        ability=ability,
                        source_character_feature_id=grant.id,
                    )
                )

    async def _reconcile_armor(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile armor-proficiency rows (per-character unique on armor_type)."""

        result = await db.execute(
            select(CharacterArmorProficiency).where(CharacterArmorProficiency.character_id == character_id)
        )
        existing = list(result.scalars().unique().all())
        present = {row.armor_type for row in existing}

        for row in existing:
            if row.source_character_feature_id == grant.id and row.armor_type not in desired.armor:
                await db.delete(row)

        for armor_type in desired.armor:
            if armor_type not in present:
                db.add(
                    CharacterArmorProficiency(
                        character_id=character_id,
                        armor_type=armor_type,
                        source_character_feature_id=grant.id,
                    )
                )

    async def _reconcile_weapons(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile weapon-proficiency rows (category rows + concrete item rows)."""

        result = await db.execute(
            select(CharacterWeaponProficiency).where(CharacterWeaponProficiency.character_id == character_id)
        )
        existing = list(result.scalars().unique().all())

        existing_categories = {row.weapon_category for row in existing if row.weapon_category is not None}
        existing_items = {row.item_id for row in existing if row.item_id is not None}
        desired_weapons = set(desired.weapons)

        for row in existing:
            marker = (row.weapon_category, row.item_id)
            if row.source_character_feature_id == grant.id and marker not in desired_weapons:
                await db.delete(row)

        for category, item_id in desired.weapons:
            if category is not None:
                if category not in existing_categories:
                    db.add(
                        CharacterWeaponProficiency(
                            character_id=character_id,
                            weapon_category=category,
                            item_id=None,
                            source_character_feature_id=grant.id,
                        )
                    )
                    existing_categories.add(category)
            elif item_id is not None:
                if item_id not in existing_items:
                    db.add(
                        CharacterWeaponProficiency(
                            character_id=character_id,
                            weapon_category=None,
                            item_id=item_id,
                            source_character_feature_id=grant.id,
                        )
                    )
                    existing_items.add(item_id)

    async def _reconcile_spells(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile granted-spell rows (unique per grant+spell)."""

        result = await db.execute(
            select(CharacterGrantedSpell).where(
                CharacterGrantedSpell.character_id == character_id,
                CharacterGrantedSpell.source_character_feature_id == grant.id,
            )
        )
        existing = list(result.scalars().unique().all())

        stored = {(row.spell_id, row.always_prepared, row.counts_against_known_limit) for row in existing}
        desired_set = set(desired.spells)

        for row in existing:
            if (row.spell_id, row.always_prepared, row.counts_against_known_limit) not in desired_set:
                await db.delete(row)

        for spell_id, always_prepared, counts_against_known_limit in desired_set:
            if (spell_id, always_prepared, counts_against_known_limit) not in stored:
                db.add(
                    CharacterGrantedSpell(
                        character_id=character_id,
                        spell_id=spell_id,
                        always_prepared=always_prepared,
                        counts_against_known_limit=counts_against_known_limit,
                        source_character_feature_id=grant.id,
                    )
                )

    @staticmethod
    def pending_groups(feature, stored_choices: list[CharacterFeatureChoice]) -> list[FeatureChoiceGroup]:
        """Return the grant's choice groups that still need picks (stored count < pick_count)."""

        picked_counts: dict[int, int] = {}
        for choice in stored_choices:
            picked_counts[choice.choice_group_id] = picked_counts.get(choice.choice_group_id, 0) + 1

        return [group for group in feature.choice_groups if picked_counts.get(group.id, 0) < group.pick_count]


__all__ = [
    "DesiredEffects",
    "FeatureGrantMaterializer",
    "ResolvedOption",
    "engine_effect_loads",
    "load_feature_effect_tree",
]
