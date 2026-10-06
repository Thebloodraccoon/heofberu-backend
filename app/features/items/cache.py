"""Item cache namespaces: what each kind of item write has to purge."""

from app.core.cache.namespaces import dependents

# Class/race/background details embed item briefs and cache per-source equipment
# under ``nested_items``; every cached feature payload renders weapon-proficiency
# item names in ``effects_summary``. An item edit must purge all of them.
ITEM_DEPENDENT_CACHE_NAMESPACES = dependents("items")

# A brand-new item is not referenced anywhere yet, and an item can only be
# deleted once nothing references it: both only change the item listings.
ITEM_OWN_CACHE_NAMESPACES = ("items",)

ITEM_CACHE_NAMESPACES = ITEM_OWN_CACHE_NAMESPACES + ITEM_DEPENDENT_CACHE_NAMESPACES
