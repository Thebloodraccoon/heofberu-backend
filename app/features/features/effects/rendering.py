"""
Server-rendered, human-readable summary of a feature's effect tree.

Turns the structured fixed effects + choice groups/options of a ``Feature``
into display text (``Feature.effects_summary``), reading skill/spell/item
names straight off each effect row's own relationship (``.skill``/
``.spell``/``.item`` — see ``feature_summary_loads`` for the eager loads
that make this synchronous, no query at render time). This is the read-side
replacement for hand-typed choice-option labels: the option's *effects* are
the single source of truth for what it grants, so this text can never drift
from what actually gets materialized (see ``FeatureGrantMaterializer``).
"""

from typing import TYPE_CHECKING

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency

if TYPE_CHECKING:
    from app.models.features.feature_model import Feature

_ABILITY_NAMES_RU = {
    AbilityScore.STR: "Силу",
    AbilityScore.DEX: "Ловкость",
    AbilityScore.CON: "Телосложение",
    AbilityScore.INT: "Интеллект",
    AbilityScore.WIS: "Мудрость",
    AbilityScore.CHA: "Харизму",
}

_ARMOR_NAMES_RU = {
    ArmorProficiency.LIGHT: "лёгкими доспехами",
    ArmorProficiency.MEDIUM: "средними доспехами",
    ArmorProficiency.HEAVY: "тяжёлыми доспехами",
    ArmorProficiency.SHIELD: "щитами",
}

_WEAPON_NAMES_RU = {
    WeaponProficiency.SIMPLE: "простым оружием",
    WeaponProficiency.MARTIAL: "воинским оружием",
}

# Nominative-case names, used in the grouped static-effects <ul> where the
# group <li> header already supplies the case ("Изменение характеристик:
# Сила +1", not "... владение Силу").
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


def _render_bundle(
    ability_effects,
    skill_effects,
    saving_throw_effects,
    armor_effects,
    weapon_effects,
    spell_effects,
) -> list[str]:
    """Render one effect bundle (a feature's fixed effects, or one choice option) into readable parts."""

    parts: list[str] = []

    parts.extend(_render_ability_short(ability_effects))

    for effect in skill_effects:
        expertise = " с экспертизой" if effect.grants_expertise else ""
        if effect.skill_id is None:
            parts.append(f"владение любым навыком на выбор{expertise}")
            continue
        name = effect.skill.name if effect.skill is not None else f"навык #{effect.skill_id}"
        parts.append(f"владение навыком «{name}»{expertise}")

    for effect in saving_throw_effects:
        parts.append(f"спасбросок {_ABILITY_NAMES_RU.get(effect.ability, effect.ability.value)}")

    for effect in armor_effects:
        parts.append(f"владение {_ARMOR_NAMES_RU.get(effect.armor_type, effect.armor_type.value)}")

    for effect in weapon_effects:
        if effect.item_id is not None:
            name = effect.item.name if effect.item is not None else f"предмет #{effect.item_id}"
            parts.append(f"владение оружием «{name}»")
        elif effect.weapon_category is not None:
            parts.append(f"владение {_WEAPON_NAMES_RU.get(effect.weapon_category, effect.weapon_category.value)}")

    for effect in spell_effects:
        if effect.spell_id is not None:
            name = effect.spell.name if effect.spell is not None else f"заклинание #{effect.spell_id}"
            parts.append(f"заклинание «{name}»")
        else:
            parts.append("любое заклинание на выбор")

    return parts


def _render_ability_short(effects) -> list[str]:
    """Nominative ``"Сила +1"`` items for the grouped "Изменение характеристик" <li>."""

    parts: list[str] = []
    for effect in effects:
        text = f"{_ABILITY_NAMES_NOM_RU.get(effect.ability, effect.ability.value)} +{effect.amount}"
        if effect.new_cap is not None:
            text += f" (потолок {effect.new_cap})"
        parts.append(text)
    return parts


def _render_saving_throw_short(effects) -> list[str]:
    """Nominative ability names for the grouped "Спасброски" <li>."""

    return [_ABILITY_NAMES_NOM_RU.get(effect.ability, effect.ability.value) for effect in effects]


def _render_skill_short(effects) -> list[str]:
    """Bare skill names for the grouped "Владения навыками" <li>."""

    parts: list[str] = []
    for effect in effects:
        expertise = " с экспертизой" if effect.grants_expertise else ""
        if effect.skill_id is None:
            parts.append(f"любым навыком на выбор{expertise}")
            continue
        name = effect.skill.name if effect.skill is not None else f"навык #{effect.skill_id}"
        parts.append(f"«{name}»{expertise}")
    return parts


def _render_armor_short(effects) -> list[str]:
    """Nominative armor-type names for the grouped "Владения доспехами" <li>."""

    return [_ARMOR_NAMES_NOM_RU.get(effect.armor_type, effect.armor_type.value) for effect in effects]


def _render_weapon_short(effects) -> list[str]:
    """Nominative weapon-category/item names for the grouped "Владения оружием" <li>."""

    parts: list[str] = []
    for effect in effects:
        if effect.item_id is not None:
            name = effect.item.name if effect.item is not None else f"предмет #{effect.item_id}"
            parts.append(f"«{name}»")
        elif effect.weapon_category is not None:
            parts.append(_WEAPON_NAMES_NOM_RU.get(effect.weapon_category, effect.weapon_category.value))
    return parts


def _render_spell_short(effects) -> list[str]:
    """Spell names (linked to ``GET /spells/{id}``) / filters for the grouped "Заклинания" <li>."""

    parts: list[str] = []
    for effect in effects:
        if effect.spell_id is not None:
            name = effect.spell.name if effect.spell is not None else f"заклинание #{effect.spell_id}"
            parts.append(f'<a href="/spells/{effect.spell_id}">{name}</a>')
        else:
            parts.append("любое на выбор")
    return parts


def _render_static_effects_html(feature: "Feature") -> str:
    """
    Render a feature's fixed effects as "Вы получаете:" followed by a
    ``<ul>`` with one ``<li>`` per non-empty effect type, in a fixed order
    (characteristics -> saving throws -> skills -> armor -> weapons ->
    spells). Returns ``""`` when the feature has no fixed effects.
    """

    groups = [
        ("Изменение характеристик", _render_ability_short(feature.ability_effects)),
        ("Спасброски", _render_saving_throw_short(feature.saving_throw_effects)),
        ("Владения навыками", _render_skill_short(feature.skill_effects)),
        ("Владения доспехами", _render_armor_short(feature.armor_effects)),
        ("Владения оружием", _render_weapon_short(feature.weapon_effects)),
        ("Заклинания", _render_spell_short(feature.spell_effects)),
    ]

    items = "".join(f"<li>{label}: {', '.join(parts)}</li>" for label, parts in groups if parts)
    return f"<p>Вы получаете:</p><ul>{items}</ul>" if items else ""


def _render_choice_groups_html(feature: "Feature") -> str:
    """
    Render every choice group as "У вас есть выбор:" followed by a ``<ul>``
    with one ``<li>`` per group. The group's ``label`` is not used — each
    ``<li>`` is just its options' effects joined by " или "; when
    ``pick_count > 1`` it's prefixed with "Выберите {pick_count}: ".
    Returns ``""`` when the feature has no choice groups.
    """

    items: list[str] = []
    for group in sorted(feature.choice_groups, key=lambda g: g.sort_order):
        option_texts = []
        for option in sorted(group.options, key=lambda o: o.sort_order):
            option_parts = _render_bundle(
                option.ability_effects,
                option.skill_effects,
                option.saving_throw_effects,
                option.armor_effects,
                option.weapon_effects,
                option.spell_effects,
            )
            option_texts.append(", ".join(option_parts) if option_parts else "—")

        body = " или ".join(option_texts)
        if group.pick_count > 1:
            body = f"Выберите {group.pick_count}: {body}"
        items.append(f"<li>{body}</li>")

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
