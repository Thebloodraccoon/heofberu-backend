"""``ArticleFilters``: the listing/search filter set, carried unchanged from the router to the repository."""

from dataclasses import dataclass

from app.constants import ArticleStatus


@dataclass(frozen=True)
class ArticleFilters:
    """
    What a ``GET /articles`` or ``GET /articles/search`` reader asked for, plus whether they may see hidden articles.

    Built once per request by ``listing.router.get_article_filters`` and passed as one value to
    ``ArticleListingService`` and ``ArticleListingRepository._filter_conditions``. A new filter is added here,
    in that dependency, and in ``_filter_conditions``, nowhere else.

    Every filter is ANDed with visibility: a non-GM filtering by author or status still only gets published,
    public articles. ``has_pending_proposals`` is GM-only and is dropped for other readers on construction.
    """

    include_hidden: bool
    statuses: tuple[ArticleStatus, ...] = ()
    article_types: tuple[str, ...] = ()
    subtype_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()
    match_all_tags: bool = False
    author_id: int | None = None
    has_pending_proposals: bool | None = None

    def __post_init__(self) -> None:
        """Ignore the GM-only ``has_pending_proposals`` for readers who can't see proposals."""

        if not self.include_hidden and self.has_pending_proposals is not None:
            object.__setattr__(self, "has_pending_proposals", None)
