"""Spell cache coordination: one invalidation point shared by every capability."""

from app.core.cache.namespaces import dependents

SPELL_CACHE_NAMESPACES = ("spells",)

# A spell's NAME is rendered into other catalogs' cached payloads (the
# ``effects_summary`` of every feature that grants it, embedded in the feature,
# feat, class/subclass/race/subrace/background and character reads), so a
# rename must purge them too. Edits that keep the name only touch ``spells``.
SPELL_NAME_DEPENDENT_NAMESPACES = dependents("spell_names")


def spell_cache_namespaces(*, name_changed: bool = False) -> tuple[str, ...]:
    """The namespaces a spell write can make stale (widened when the spell was renamed)."""

    return SPELL_CACHE_NAMESPACES + SPELL_NAME_DEPENDENT_NAMESPACES if name_changed else SPELL_CACHE_NAMESPACES
