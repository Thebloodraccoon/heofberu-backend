"""Feature cache coordination: one invalidation point shared by every capability."""

from app.constants import FeatureSourceType
from app.core.cache import invalidate

FEATURE_CACHE_NAMESPACES = ("features",)

# A write touching one feature purges the owning catalog's list namespace
# (and only that one) so its cached ``GET /{source}/features`` goes stale.
# FEAT/OTHER features are standalone — no catalog owns them.
SOURCE_FEATURE_LIST_NAMESPACE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_features",
    FeatureSourceType.SUBCLASS: "subclass_features",
    FeatureSourceType.RACE: "race_features",
    FeatureSourceType.SUBRACE: "subrace_features",
    FeatureSourceType.BACKGROUND: "background_features",
    FeatureSourceType.FEAT: None,
    FeatureSourceType.OTHER: None,
}

# The parent catalog read namespace holding that source's cached FULL
# response. A write touching one feature must also purge it: the parent
# detail read embeds its features (name, effects, has_static_effects/
# has_choices, effects_summary), so the whole cached payload would go stale
# otherwise. Subrace detail is cached under ``races`` and subclass detail
# under ``classes``.
SOURCE_PARENT_READ_NAMESPACE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "classes",
    FeatureSourceType.SUBCLASS: "classes",
    FeatureSourceType.RACE: "races",
    FeatureSourceType.SUBRACE: "races",
    FeatureSourceType.BACKGROUND: "backgrounds",
    FeatureSourceType.FEAT: None,
    FeatureSourceType.OTHER: None,
}


async def invalidate_feature_cache() -> None:
    """Purge the shared ``features`` namespace (``GET /features`` + ``GET /features/{id}``)."""

    for namespace in FEATURE_CACHE_NAMESPACES:
        await invalidate(namespace)


async def purge_feature_cache_for_source(source_type: FeatureSourceType) -> None:
    """
    Purge every cache namespace a write touching ONE feature of
    ``source_type`` can make stale: the shared ``features`` namespace, the
    owning catalog's feature-list namespace, and the owning catalog's own
    parent-read namespace. Every write that changes a feature's identity,
    fixed effects, or choice groups must call this — not just
    ``invalidate_feature_cache`` — or the parent catalog's cached detail/
    list reads keep serving the pre-edit feature payload.
    """

    await invalidate_feature_cache()

    list_namespace = SOURCE_FEATURE_LIST_NAMESPACE.get(source_type)
    if list_namespace is not None:
        await invalidate(list_namespace)

    parent_namespace = SOURCE_PARENT_READ_NAMESPACE.get(source_type)
    if parent_namespace is not None:
        await invalidate(parent_namespace)
