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

    for effect in ability_effects:
        text = f"+{effect.amount} к {_ABILITY_NAMES_RU.get(effect.ability, effect.ability.value)}"
        if effect.new_cap is not None:
            text += f" (потолок {effect.new_cap})"
        parts.append(text)

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
            continue
        filters = []
        if effect.spell_school is not None:
            filters.append(f"школы {effect.spell_school.value}")
        if effect.spell_level_max is not None:
            filters.append(f"не выше {effect.spell_level_max.value} уровня")
        parts.append(" ".join(["любое заклинание", *filters]))

    return parts


def render_effects_summary(feature: "Feature") -> str:
    """
    Human-readable text summarizing a feature's fixed effects and each
    choice group's options. Purely synchronous — every name it needs
    (skill/spell/item) is read off an already eager-loaded relationship;
    see ``feature_summary_loads`` for the required eager loads.
    """

    lines: list[str] = []

    fixed_parts = _render_bundle(
        feature.ability_effects,
        feature.skill_effects,
        feature.saving_throw_effects,
        feature.armor_effects,
        feature.weapon_effects,
        feature.spell_effects,
    )
    if fixed_parts:
        lines.append("Даёт: " + ", ".join(fixed_parts) + ".")

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

        label = group.label or "Выбор"
        options_joined = "; ".join(f"[{i + 1}] {text}" for i, text in enumerate(option_texts))
        lines.append(f"{label} (выберите {group.pick_count} из {len(group.options)}): {options_joined}.")

    return "\n".join(lines)


__all__ = ["render_effects_summary"]
