"""
Materializer: reconcile a character's effect rows against one feature grant's effect tree.

A grant's "desired" effect surface is the union of:
- the feature's fixed (``feature_id``-owned) effect rows, and
- the effect rows bundled inside the options the player picked for the
  grant's choice groups.

For skills/saves/armor/weapons, the materializer diffs that against THIS
GRANT'S OWN rows in ``character_proficiencies``
(``source_character_feature_id == grant.id``) and writes the delta: rows
whose effect vanished are deleted, missing ones are inserted with
``source_type=FEATURE``. It never looks at (or touches) another grant's
rows, a GM row, or a CLASS_CHOICE/RACE/BACKGROUND row for the same
proficiency — two sources both granting the same skill are two legitimate
rows, not a collision (see ``CharacterProficiency`` for the resolution
algorithm that turns these rows into "does the character currently have
it"). Skill ``is_expertise`` on this grant's own row is monotonic (an
effect wanting expertise can upgrade it, never downgrades it) — whether the
character's *effective* expertise is on doesn't depend on this row alone,
it's resolved across every row for that skill plus any GM override.

Granted-spell rows (``character_granted_spells``) are a separate table,
untouched by this refactor, and still reconcile the old way (grant-scoped,
one row per grant+spell).

Never commits — the caller's transaction owns persistence.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.character.character_spell_model import CharacterGrantedSpell
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption
from app.models.features.feature_model import Feature


_OPTION_EFFECT_ATTRS = (
    "ability_effects",
    "skill_effects",
    "saving_throw_effects",
    "armor_effects",
    "weapon_effects",
    "spell_effects",
)


def choice_option_effect_loads(base_loader) -> list:
    """
    Chain onto ``base_loader`` (a ``selectinload`` chain ending at a
    ``FeatureChoiceOption``, e.g. a stored ``CharacterFeatureChoice``'s
    ``.choice_option``) the six effect-type loads a chosen option's bundle
    needs — used wherever a resolved pick's effects are read back (see
    ``ChosenOptionResponse``).
    """

    return [base_loader.selectinload(getattr(FeatureChoiceOption, attr)) for attr in _OPTION_EFFECT_ATTRS]


def engine_effect_loads() -> list:
    """Eager loads for the whole feature-engine effect tree (shared loader)."""

    option_effect_attrs = _OPTION_EFFECT_ATTRS

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
    spells: set = field(default_factory=set)


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
            desired.spells.add(effect.spell_id)

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
            desired.spells.add(spell_id)

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
        await self._reconcile_skills(db, character_id, grant, feature, desired)
        await self._reconcile_saves(db, character_id, grant, feature, desired)
        await self._reconcile_armor(db, character_id, grant, feature, desired)
        await self._reconcile_weapons(db, character_id, grant, feature, desired)
        await self._reconcile_spells(db, character_id, grant, desired)

    @staticmethod
    def _new_proficiency(
        character_id: int,
        grant: CharacterFeature,
        feature,
        proficiency_type: ProficiencyType,
        **discriminator,
    ) -> CharacterProficiency:
        """Build one grant-sourced ``CharacterProficiency`` row (``source_type=FEATURE``)."""

        return CharacterProficiency(
            character_id=character_id,
            proficiency_type=proficiency_type,
            source_type=ProficiencySourceType.FEATURE,
            action=ProficiencyAction.GRANT,
            source_character_feature_id=grant.id,
            grant_source=grant.grant_source,
            feature_id=feature.id,
            feature_source_type=feature.source_type,
            **discriminator,
        )

    async def _own_rows(
        self, db: AsyncSession, character_id: int, grant: CharacterFeature, proficiency_type: ProficiencyType
    ) -> list[CharacterProficiency]:
        """Fetch this grant's own ``CharacterProficiency`` rows of one kind."""

        result = await db.execute(
            select(CharacterProficiency).where(
                CharacterProficiency.character_id == character_id,
                CharacterProficiency.proficiency_type == proficiency_type,
                CharacterProficiency.source_character_feature_id == grant.id,
            )
        )
        return list(result.scalars().unique().all())

    async def _reconcile_by_key(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        proficiency_type: ProficiencyType,
        desired_keys,
        key_of,
        build_kwargs,
        on_keep=None,
    ) -> None:
        """
        Generic keyed diff: delete this grant's own rows of ``proficiency_type``
        whose ``key_of`` isn't in ``desired_keys``, insert the missing ones
        (built via ``build_kwargs``). ``on_keep``, if given, runs on every
        already-present row whose key is still desired (used by skills to
        upgrade ``is_expertise`` without ever downgrading it).
        """

        own = {key_of(row): row for row in await self._own_rows(db, character_id, grant, proficiency_type)}

        for key, row in own.items():
            if key not in desired_keys:
                await db.delete(row)

        for key in desired_keys:
            row = own.get(key)
            if row is not None:
                if on_keep is not None:
                    on_keep(row, key)
                continue

            db.add(self._new_proficiency(character_id, grant, feature, proficiency_type, **build_kwargs(key)))

    async def _reconcile_skills(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile this grant's own skill-proficiency rows (preserving expertise upgrades)."""

        def on_keep(row: CharacterProficiency, skill_id: int) -> None:
            if desired.skills[skill_id] and not row.is_expertise:
                row.is_expertise = True

        await self._reconcile_by_key(
            db,
            character_id,
            grant,
            feature,
            ProficiencyType.SKILL,
            desired_keys=set(desired.skills),
            key_of=lambda row: row.skill_id,
            build_kwargs=lambda skill_id: {"skill_id": skill_id, "is_expertise": desired.skills[skill_id]},
            on_keep=on_keep,
        )

    async def _reconcile_saves(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile this grant's own saving-throw proficiency rows."""

        await self._reconcile_by_key(
            db,
            character_id,
            grant,
            feature,
            ProficiencyType.SAVING_THROW,
            desired_keys=desired.saving_throws,
            key_of=lambda row: row.ability,
            build_kwargs=lambda ability: {"ability": ability},
        )

    async def _reconcile_armor(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile this grant's own armor-proficiency rows."""

        await self._reconcile_by_key(
            db,
            character_id,
            grant,
            feature,
            ProficiencyType.ARMOR,
            desired_keys=desired.armor,
            key_of=lambda row: row.armor_type,
            build_kwargs=lambda armor_type: {"armor_type": armor_type},
        )

    async def _reconcile_weapons(
        self,
        db: AsyncSession,
        character_id: int,
        grant: CharacterFeature,
        feature,
        desired: DesiredEffects,
    ) -> None:
        """Reconcile this grant's own weapon-proficiency rows (category rows + concrete item rows)."""

        await self._reconcile_by_key(
            db,
            character_id,
            grant,
            feature,
            ProficiencyType.WEAPON,
            desired_keys=set(desired.weapons),
            key_of=lambda row: (row.weapon_category, row.item_id),
            build_kwargs=lambda key: (
                {"weapon_category": key[0]} if key[0] is not None else {"item_id": key[1]}
            ),
        )

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

        stored = {row.spell_id for row in existing}

        for row in existing:
            if row.spell_id not in desired.spells:
                await db.delete(row)

        for spell_id in desired.spells:
            if spell_id not in stored:
                db.add(
                    CharacterGrantedSpell(
                        character_id=character_id,
                        spell_id=spell_id,
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
    "choice_option_effect_loads",
    "engine_effect_loads",
    "load_feature_effect_tree",
]
