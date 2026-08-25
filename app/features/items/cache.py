"""Item cache coordination: one invalidation point shared by every capability."""

from app.core.cache import invalidate

# An item edit reaches far beyond the ``items`` listing:
#   - ``nested_items``: per-source starting-equipment listings embed
#     ``ItemBriefResponse`` rows joined from this table;
#   - ``classes`` / ``backgrounds``: the FullResponses embed starting-item
#     briefs too.
ITEM_CACHE_NAMESPACES = ("items", "nested_items", "classes", "backgrounds")


async def invalidate_item_cache() -> None:
    """
    Purge every cache namespace an item read can hit.

    ``GET /items`` (``items`` namespace) is served from cache, and so are
    the nested item listings and every class/background full response
    that embeds item briefs. Any write to an item — catalog CRUD via
    ``/items`` or a class/background starting-equipment list referencing
    it — must call this after its transaction commits. The
    class/background catalogs also include ``"items"`` in their own
    ``cache_namespaces`` for the reverse direction.
    """

    for namespace in ITEM_CACHE_NAMESPACES:
        await invalidate(namespace)
