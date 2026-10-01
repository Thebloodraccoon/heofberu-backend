"""
The single proficiency resolver shared by the read surface and the GM writes.

Every source's claim on a proficiency is a :class:`ProficiencyEntry`: a
stored row (class/race/background choice or the GM layer) or a feature/feat
grant's computed effect. Entries sharing a key resolve like this:

- a GM ``REVOKE`` entry excludes the proficiency outright;
- otherwise any entry grants it;
- expertise: a GM ``GRANT`` entry with an explicit ``is_expertise`` (True or
  False) decides alone, so a GM can also clear expertise that another source
  gives; without an explicit GM decision any source's expertise counts.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.features.characters.grants.effects import GrantEffects
from app.features.characters.proficiencies.schemas import ProficiencySource
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.features.feature_model import Feature


@dataclass(frozen=True)
class ProficiencyEntry:
    """One source's claim on a proficiency."""

    key: tuple
    source: ProficiencySource
    is_expertise: bool = False
    revoke: bool = False
    gm_expertise: bool | None = None

    @property
    def is_gm(self) -> bool:
        """Whether this entry is the GM layer (as opposed to a class/race/background row or a feature grant)."""

        return self.source.source_type == ProficiencySourceType.GM


@dataclass(frozen=True)
class ResolvedProficiency:
    """A proficiency the character currently has, with every source that grants it."""

    key: tuple
    sources: list[ProficiencySource]
    is_expertise: bool


def proficiency_key(proficiency_type: ProficiencyType, **discriminator) -> tuple:
    """The ``(proficiency_type, *discriminator)`` key built from the keyword discriminator a GM write passes."""

    if proficiency_type == ProficiencyType.WEAPON:
        return (proficiency_type, discriminator.get("weapon_category"), discriminator.get("item_id"))

    (value,) = discriminator.values()
    return (proficiency_type, value)


def row_key(row: CharacterProficiency) -> tuple:
    """The key every stored row of the same proficiency shares."""

    proficiency_type = ProficiencyType(row.proficiency_type)

    if proficiency_type == ProficiencyType.SKILL:
        return (proficiency_type, row.skill_id)
    if proficiency_type == ProficiencyType.SAVING_THROW:
        return (proficiency_type, row.ability)
    if proficiency_type == ProficiencyType.ARMOR:
        return (proficiency_type, row.armor_type)

    return (proficiency_type, row.weapon_category, row.item_id)


def row_entry(row: CharacterProficiency) -> ProficiencyEntry:
    """A stored row (class/race/background choice or GM override)."""

    is_gm = row.source_type == ProficiencySourceType.GM
    gm_grant = is_gm and row.action != ProficiencyAction.REVOKE
    return ProficiencyEntry(
        key=row_key(row),
        source=ProficiencySource(source_type=row.source_type, actor_user_id=row.actor_user_id),
        is_expertise=bool(row.is_expertise),
        revoke=is_gm and not gm_grant,
        gm_expertise=row.is_expertise if gm_grant else None,
    )


def feature_source(feature: Feature) -> ProficiencySource:
    """The source tag of a feature/feat grant."""

    return ProficiencySource(
        source_type=ProficiencySourceType.FEATURE,
        feature_id=feature.id,
        feature_name=feature.name,
        feature_source_type=feature.source_type,
    )


def feature_entries(feature: Feature, effects: GrantEffects) -> list[ProficiencyEntry]:
    """Every proficiency a feature/feat grant's computed effects give."""

    source = feature_source(feature)
    entries = [
        ProficiencyEntry((ProficiencyType.SKILL, skill_id), source, is_expertise=expertise)
        for skill_id, expertise in effects.skills.items()
    ]
    entries += [ProficiencyEntry((ProficiencyType.SAVING_THROW, ability), source) for ability in effects.saving_throws]
    entries += [ProficiencyEntry((ProficiencyType.ARMOR, armor_type), source) for armor_type in effects.armor]
    entries += [ProficiencyEntry((ProficiencyType.WEAPON, *weapon), source) for weapon in effects.weapons]
    return entries


def resolve_group(key: tuple, group: list[ProficiencyEntry]) -> ResolvedProficiency | None:
    """Resolve the entries of ONE proficiency; ``None`` when the character does not have it."""

    if not group or any(entry.revoke for entry in group):
        return None

    explicit = next((entry.gm_expertise for entry in group if entry.gm_expertise is not None), None)
    is_expertise = explicit if explicit is not None else any(entry.is_expertise for entry in group)

    return ResolvedProficiency(key=key, sources=[entry.source for entry in group], is_expertise=is_expertise)


def resolve_all(entries: Iterable[ProficiencyEntry]) -> list[ResolvedProficiency]:
    """Group entries by proficiency and resolve each; revoked proficiencies are omitted."""

    grouped: dict[tuple, list[ProficiencyEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.key].append(entry)

    resolved = (resolve_group(key, group) for key, group in grouped.items())
    return [proficiency for proficiency in resolved if proficiency is not None]
