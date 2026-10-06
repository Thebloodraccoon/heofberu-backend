"""
The cache dependency map: which cached namespaces embed data of which entity.

A cached payload that renders another entity's name or id (a feature's
``effects_summary`` naming a skill, a spell listing naming its classes, ...) goes
stale when that entity is written. ``CACHE_DEPENDENTS`` is the one place that
declares those edges, keyed by the written *entity* (not necessarily a cache
namespace: subclasses and subraces cache under ``classes`` / ``races``). The
per-module ``cache.py`` files derive their purge sets from it through
:func:`dependents`, so a new embedding is declared once and every writer picks it up.

``tests/unit/core/test_cache_namespace_graph.py`` fails when a namespace used by a
``@use_cache`` method has no purge path or when this map names a namespace nothing caches.
"""

FEATURE_PAYLOAD_NAMESPACES = (
    "features",
    "feats",
    "class_features",
    "subclass_features",
    "race_features",
    "subrace_features",
    "background_features",
)
"""Namespaces whose payloads carry a feature's ``effects_summary`` (names of skills, items, spells)."""

CATALOG_DETAIL_NAMESPACES = ("classes", "races", "backgrounds")
"""Namespaces whose detail reads embed brief rows of skills/items and their features' summaries."""

CACHE_DEPENDENTS: dict[str, tuple[str, ...]] = {
    "skills": (*CATALOG_DETAIL_NAMESPACES, *FEATURE_PAYLOAD_NAMESPACES),
    "items": ("nested_items", *CATALOG_DETAIL_NAMESPACES, *FEATURE_PAYLOAD_NAMESPACES),
    "spell_names": (*CATALOG_DETAIL_NAMESPACES, *FEATURE_PAYLOAD_NAMESPACES, "characters"),
    "classes": ("spells",),
    "subclasses": ("spells",),
    "races": ("spells",),
    "subraces": ("spells",),
    "tags": ("races", "backgrounds", "articles"),
    "users": ("articles",),
}
"""Entity written -> namespaces whose cached payloads embed its name/id (besides its own)."""


def dependents(entity: str) -> tuple[str, ...]:
    """Namespaces a write of ``entity`` makes stale besides the entity's own (``()`` when none are declared)."""

    return CACHE_DEPENDENTS.get(entity, ())
