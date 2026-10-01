"""Feature cache coordination: one invalidation point shared by every capability."""

from app.constants import FeatureSourceType
from app.core.base.transaction import invalidate_after_commit

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
    FeatureSourceType.FEAT: "feats",
    FeatureSourceType.OTHER: None,
}


def feature_namespaces(source_type: FeatureSourceType) -> list[str]:
    """Every cache namespace a write touching one ``source_type`` feature can make stale."""

    namespaces = list(FEATURE_CACHE_NAMESPACES)
    for mapping in (SOURCE_FEATURE_LIST_NAMESPACE, SOURCE_PARENT_READ_NAMESPACE):
        namespace = mapping.get(source_type)
        if namespace is not None:
            namespaces.append(namespace)

    return namespaces


async def invalidate_feature_cache_after_commit(db, source_type: FeatureSourceType) -> None:
    """Schedule the purge of :func:`feature_namespaces` for after the surrounding transaction commits."""

    await invalidate_after_commit(db, *feature_namespaces(source_type))
