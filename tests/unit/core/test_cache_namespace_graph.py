"""The cache dependency map and the namespaces actually cached by services must agree."""

import importlib
import inspect
import pkgutil

import pytest

import app.core.base as core_base
from app.core.cache.namespaces import CACHE_DEPENDENTS, FEATURE_PAYLOAD_NAMESPACES, dependents
import app.features as features_package
from app.features.features.cache import SOURCE_FEATURE_LIST_NAMESPACE, SOURCE_PARENT_READ_NAMESPACE

KEY_BUILDER_NAMESPACES = {"characters"}
"""Cached through a custom ``key_builder`` on a service without ``cache_namespaces``."""


def _import_all(package) -> list:
    modules = []
    for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        if info.name.endswith((".router", ".dependencies")):
            continue
        modules.append(importlib.import_module(info.name))
    return modules


def _classes() -> set[type]:
    found: set[type] = set()
    for module in [*_import_all(features_package), *_import_all(core_base)]:
        for _, cls in inspect.getmembers(module, inspect.isclass):
            found.add(cls)
    return found


def _cached_namespaces() -> dict[str, set[str]]:
    """Namespace -> names of the service classes caching under it."""

    cached: dict[str, set[str]] = {}
    for cls in _classes():
        declared = getattr(cls, "cache_namespaces", ())
        for name in dir(cls):
            marker = getattr(getattr(cls, name, None), "__use_cache__", None)
            if marker is None:
                continue
            namespace = marker["namespace"] or (declared[0] if declared else None)
            if namespace is None:
                continue
            cached.setdefault(namespace, set()).add(cls.__name__)

    return cached


@pytest.mark.unit
class TestNamespaceGraph:
    def test_the_scan_finds_the_known_catalogs(self):
        cached = set(_cached_namespaces())

        assert {"classes", "races", "backgrounds", "spells", "features", "feats", "skills", "items"} <= cached
        assert {"nested_items", "class_features", "race_features", "articles", "users", "tags"} <= cached

    def test_every_cached_namespace_has_a_service_that_purges_it(self):
        purged_by_services = {
            namespace
            for cls in _classes()
            if getattr(cls, "cache_namespaces", ())
            for namespace in cls.cache_namespaces
        }
        unpurged = set(_cached_namespaces()) - purged_by_services

        assert unpurged == set()

    def test_every_dependency_target_is_a_cached_namespace(self):
        cached = set(_cached_namespaces()) | KEY_BUILDER_NAMESPACES
        targets = {namespace for values in CACHE_DEPENDENTS.values() for namespace in values}

        assert targets - cached == set()

    def test_feature_source_maps_only_name_cached_namespaces(self):
        cached = set(_cached_namespaces())
        names = {
            namespace
            for mapping in (SOURCE_FEATURE_LIST_NAMESPACE, SOURCE_PARENT_READ_NAMESPACE)
            for namespace in mapping.values()
            if namespace is not None
        }

        assert names - cached == set()

    def test_feature_payload_namespaces_are_cached(self):
        assert set(FEATURE_PAYLOAD_NAMESPACES) <= set(_cached_namespaces())

    @pytest.mark.parametrize("entity", ["classes", "subclasses", "races", "subraces"])
    def test_spell_listings_are_purged_when_a_named_entity_changes(self, entity):
        assert "spells" in dependents(entity)

    def test_items_purge_every_catalog_that_renders_their_names(self):
        assert {"races", "classes", "backgrounds", "nested_items", *FEATURE_PAYLOAD_NAMESPACES} <= set(
            dependents("items")
        )

    def test_unknown_entities_have_no_dependents(self):
        assert dependents("nothing") == ()
