"""Background cache namespaces: what each kind of write has to purge."""

# Base fields, skills, tags and suggestions only show up in background reads.
BACKGROUND_CACHE_NAMESPACES = ("backgrounds",)

# Starting equipment is also cached per source under ``nested_items``.
BACKGROUND_ITEMS_CACHE_NAMESPACES = ("backgrounds", "nested_items")

# Deleting a background cascades to its features and starting equipment.
BACKGROUND_DELETE_CACHE_NAMESPACES = ("backgrounds", "background_features", "features", "nested_items")
