"""
Server-rendered, human-readable summary of a feature's effect tree.

Turns the structured fixed effects + choice groups/options of a ``Feature``
into display text (``Feature.effects_summary``), reading skill/spell/item
names straight off each effect row's own relationship (``.skill``/
``.spell``/``.item`` — see ``feature_summary_loads`` for the eager loads
that make this synchronous, no query at render time). This is the read-side
replacement for hand-typed choice-option labels: the option's *effects* are
the single source of truth for what it grants, so this text can never drift
from what a grant actually gives (computed on read, see
``app.features.characters.grants.effects``).

The result is HTML (``<p>``/``<ul>``/``<li>``/``<a>``): every catalog name that
is interpolated into it is HTML-escaped, so a name can never inject markup.
"""

from html import escape
from typing import TYPE_CHECKING

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    ChoiceType,
    SkillEffectMode,
    SpellLevel,
    SpellSchool,
    WeaponProficiency,
)

if TYPE_CHECKING:
    from app.models.features.feature_model import Feature

# Nominative names: the grouped static-effects <ul> supplies the case via its
# <li> header ("Изменение характеристик: Сила +1").
_ABILITY_NAMES_NOM_RU = {
    AbilityScore.STR: "Сила",
    AbilityScore.DEX: "Ловкость",
    AbilityScore.CON: "Телосложение",
    AbilityScore.INT: "Интеллект",
    AbilityScore.WIS: "Мудрость",
    AbilityScore.CHA: "Харизма",
}

_ARMOR_NAMES_NOM_RU = {
    ArmorProficiency.LIGHT: "лёгкие доспехи",
    ArmorProficiency.MEDIUM: "средние доспехи",
    ArmorProficiency.HEAVY: "тяжёлые доспехи",
    ArmorProficiency.SHIELD: "щиты",
}

_WEAPON_NAMES_NOM_RU = {
    WeaponProficiency.SIMPLE: "простое оружие",
    WeaponProficiency.MARTIAL: "воинское оружие",
}

_SPELL_SCHOOL_NAMES_RU = {
    SpellSchool.ABJURATION: "Ограждение",
    SpellSchool.CONJURATION: "Вызов",
    SpellSchool.DIVINATION: "Прорицание",
    SpellSchool.ENCHANTMENT: "Очарование",
    SpellSchool.EVOCATION: "Воплощение",
    SpellSchool.ILLUSION: "Иллюзия",
    SpellSchool.NECROMANCY: "Некромантия",
    SpellSchool.TRANSMUTATION: "Превращение",
}

_SPELL_LEVELS = tuple(SpellLevel)


def _skill_name(effect) -> str:
    """HTML-escaped catalog name of a skill effect's skill (id fallback)."""

    return escape(effect.skill.name if effect.skill is not None else f"навык #{effect.skill_id}")


def _item_name(effect) -> str:
    """HTML-escaped catalog name of a weapon effect's item (id fallback)."""

    return escape(effect.item.name if effect.item is not None else f"предмет #{effect.item_id}")


def _spell_name(effect) -> str:
    """HTML-escaped catalog name of a spell effect's spell (id fallback)."""

    return escape(effect.spell.name if effect.spell is not None else f"заклинание #{effect.spell_id}")


def _render_ability_short(effects) -> list[str]:
    """Nominative signed ``"Сила +1"`` / ``"Сила -1"`` items for the grouped "Изменение характеристик" <li>."""

    parts: list[str] = []
    for effect in effects:
        text = f"{_ABILITY_NAMES_NOM_RU.get(effect.ability, effect.ability.value)} {effect.amount:+d}"
        if effect.new_cap is not None:
            text += f" (потолок {effect.new_cap})"
        parts.append(text)
    return parts


def _render_saving_throw_short(effects) -> list[str]:
    """Nominative ability names for the grouped "Спасброски" <li>."""

    return [_ABILITY_NAMES_NOM_RU.get(effect.ability, effect.ability.value) for effect in effects]


# What each skill-effect mode adds after the skill name in the "Владения навыками" <li>.
_SKILL_MODE_SUFFIX_RU = {
    SkillEffectMode.PROFICIENCY: "",
    SkillEffectMode.PROFICIENCY_AND_EXPERTISE: " с экспертизой",
    SkillEffectMode.EXPERTISE: " — только экспертиза (нужно владение)",
    SkillEffectMode.UPGRADE: " (экспертиза, если уже есть владение)",
}


def _render_skill_short(effects) -> list[str]:
    """Bare skill names for the grouped "Владения навыками" <li>, each with its mode's suffix."""

    parts: list[str] = []
    for effect in effects:
        suffix = _SKILL_MODE_SUFFIX_RU.get(effect.mode, "")
        name = "любым навыком на выбор" if effect.skill_id is None else f"«{_skill_name(effect)}»"
        parts.append(f"{name}{suffix}")
    return parts


def _render_armor_short(effects) -> list[str]:
    """Nominative armor-type / concrete armor names for the grouped "Владения доспехами" <li>."""

    parts: list[str] = []
    for effect in effects:
        if effect.item_id is not None:
            parts.append(f"«{_item_name(effect)}»")
        elif effect.armor_type is not None:
            parts.append(_ARMOR_NAMES_NOM_RU.get(effect.armor_type, effect.armor_type.value))
    return parts


def _render_weapon_short(effects) -> list[str]:
    """Nominative weapon-category/item names for the grouped "Владения оружием" <li>."""

    parts: list[str] = []
    for effect in effects:
        if effect.item_id is not None:
            parts.append(f"«{_item_name(effect)}»")
        elif effect.weapon_category is not None:
            parts.append(_WEAPON_NAMES_NOM_RU.get(effect.weapon_category, effect.weapon_category.value))
    return parts


def _spell_level_range(min_level, max_level) -> str | None:
    """``"заговор"`` / ``"3-го уровня"`` / ``"1–5-го уровня"`` / ``"до 5-го уровня"`` for a filter's level range."""

    low = _SPELL_LEVELS.index(min_level) if min_level is not None else None
    high = _SPELL_LEVELS.index(max_level) if max_level is not None else None

    if low is not None and low == high:
        return "заговор" if low == 0 else f"{low}-го уровня"
    if high == 0:
        return "заговор"
    if low is not None and high is not None:
        return f"заговор или до {high}-го уровня" if low == 0 else f"{low}–{high}-го уровня"
    if low:
        return f"от {low}-го уровня"
    if high is not None:
        return f"до {high}-го уровня"
    return None


def describe_spell_filter(effect) -> list[str]:
    """
    The conditions of an open ("any spell") effect's filter as short Russian phrases; ``[]`` = any spell
    at all. Class names come from ``effect.class_names`` when known, else only how many lists are allowed.
    """

    conditions: list[str] = []

    level_range = _spell_level_range(effect.min_level, effect.max_level)
    if effect.castable_only:
        cantrips_allowed = effect.min_level in (None, SpellLevel.CANTRIP)
        conditions.append("заговор или доступного вам уровня" if cantrips_allowed else "доступного вам уровня")
        if level_range is not None and level_range != "заговор":
            conditions.append(level_range)
    elif level_range is not None:
        conditions.append(level_range)

    if effect.schools:
        schools = ", ".join(_SPELL_SCHOOL_NAMES_RU.get(school, school.value) for school in effect.schools)
        conditions.append(f"школа: {schools}")

    if effect.ritual_only:
        conditions.append("ритуал")

    if effect.class_ids:
        names = getattr(effect, "class_names", None)
        if names:
            conditions.append(f"из списка: {', '.join(names)}")
        else:
            conditions.append("из списка класса" if len(effect.class_ids) == 1 else "из списков выбранных классов")

    return conditions


def _render_spell_short(effects) -> list[str]:
    """Spell names (linked to ``/catalog/spells/{id}``) / filters for the grouped "Заклинания" <li>."""

    parts: list[str] = []
    for effect in effects:
        if effect.spell_id is not None:
            parts.append(f'<a href="/catalog/spells/{effect.spell_id}">{_spell_name(effect)}</a>')
            continue

        conditions = [escape(condition) for condition in describe_spell_filter(effect)]
        parts.append(f"любое на выбор ({'; '.join(conditions)})" if conditions else "любое на выбор")
    return parts


# Per choice_type: (label of the <li>, effect attribute, short renderer) — shared by the fixed-effects list and
# the choice groups, which are both rendered in this order.
_EFFECT_RENDERERS = {
    ChoiceType.ABILITY_SCORE: ("Изменение характеристик", "ability_effects", _render_ability_short),
    ChoiceType.SAVING_THROW: ("Спасброски", "saving_throw_effects", _render_saving_throw_short),
    ChoiceType.SKILL: ("Владения навыками", "skill_effects", _render_skill_short),
    ChoiceType.ARMOR: ("Владения доспехами", "armor_effects", _render_armor_short),
    ChoiceType.WEAPON: ("Владения оружием", "weapon_effects", _render_weapon_short),
    ChoiceType.SPELL: ("Заклинания", "spell_effects", _render_spell_short),
}


def _render_static_effects_html(feature: "Feature") -> str:
    """
    Render a feature's fixed effects as "Вы получаете:" followed by a
    ``<ul>`` with one ``<li>`` per non-empty effect type, in ``_EFFECT_RENDERERS`` order
    (characteristics -> saving throws -> skills -> armor -> weapons -> spells).
    Returns ``""`` when the feature has no fixed effects.
    """

    groups = [(label, short(getattr(feature, attr))) for label, attr, short in _EFFECT_RENDERERS.values()]
    items = "".join(f"<li>{label}: {', '.join(parts)}</li>" for label, parts in groups if parts)
    return f"<p>Вы получаете:</p><ul>{items}</ul>" if items else ""


def _render_choice_groups_html(feature: "Feature") -> str:
    """
    Render every choice group as "У вас есть выбор:" followed by a ``<ul>``
    with one ``<li>`` per group: ``"{Label}: {option} или {option}"``, with the count
    in parentheses before the colon when ``pick_count > 1``
    (e.g. ``"Владения доспехами (2): лёгкие доспехи или тяжёлые доспехи"``), the
    label following the group's ``choice_type`` as in the fixed-effects list. The groups come in that
    list's order (characteristics, saving throws, skills, armor, weapons, spells), then by ``sort_order``.
    The group's ``label`` field is not used. Returns ``""`` when the feature has no choice groups.
    """

    type_order = list(_EFFECT_RENDERERS)
    items: list[str] = []
    for group in sorted(feature.choice_groups, key=lambda g: (type_order.index(g.choice_type), g.sort_order)):
        label, attr, short = _EFFECT_RENDERERS[group.choice_type]
        options = sorted(group.options, key=lambda o: o.sort_order)
        body = " или ".join(", ".join(short(getattr(option, attr))) or "—" for option in options)

        count = f" ({group.pick_count})" if group.pick_count > 1 else ""
        items.append(f"<li>{label}{count}: {body}</li>")

    return f"<p>У вас есть выбор:</p><ul>{''.join(items)}</ul>" if items else ""


def render_effects_summary(feature: "Feature") -> str:
    """
    Human-readable text summarizing a feature's fixed effects and each
    choice group's options. Purely synchronous — every name it needs
    (skill/spell/item) is read off an already eager-loaded relationship;
    see ``feature_summary_loads`` for the required eager loads.
    """

    lines: list[str] = []

    static_html = _render_static_effects_html(feature)
    if static_html:
        lines.append(static_html)

    choice_html = _render_choice_groups_html(feature)
    if choice_html:
        if lines:
            lines.append("")
        lines.append(choice_html)

    return "\n".join(lines)


__all__ = ["render_effects_summary"]
