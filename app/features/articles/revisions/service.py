"""Article history reads: list, one snapshot, and the diff between two versions."""

import difflib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, paginate
from app.features.articles.revisions.repository import ArticleRevisionRepository
from app.features.articles.revisions.schemas import (
    ArticleRevisionBrief,
    ArticleRevisionDiff,
    ArticleRevisionResponse,
    FieldChange,
)
from app.models.articles.article_revision_model import ArticleRevision

#: ``sort`` name baked into history cursors (keyed by ``version``), so another listing's cursor is a 422.
CURSOR_SORT = "revisions"

#: Scalar content fields compared by the diff (the body gets a text diff of its own).
DIFF_FIELDS = ("title", "excerpt", "article_type", "subtype_id", "visibility")


def _value(revision: ArticleRevision | None, field: str):
    """A field of the snapshot as a JSON-friendly value; ``None`` for the (nonexistent) version before the first."""

    value = getattr(revision, field, None)
    return getattr(value, "value", value)


def build_diff(
    old: ArticleRevision | None, new, *, version: int | None = None, label: str | None = None
) -> ArticleRevisionDiff:
    """
    Diff ``new`` against ``old`` (``None`` = nothing before, i.e. everything is an addition).

    ``new`` is any object with the content fields (a revision, or a proposal with an explicit ``version``/``label``).
    """

    version = new.version if version is None else version

    changes = {
        field: FieldChange(old=_value(old, field), new=_value(new, field))
        for field in DIFF_FIELDS
        if _value(old, field) != _value(new, field)
    }
    body_diff = difflib.unified_diff(
        (old.body_markdown if old else "").splitlines(),
        new.body_markdown.splitlines(),
        fromfile=f"v{old.version}" if old else "empty",
        tofile=label or f"v{version}",
        lineterm="",
    )
    return ArticleRevisionDiff(
        version=version, against=old.version if old else 0, fields=changes, body_diff="\n".join(body_diff)
    )


class ArticleRevisionsService:
    """Read side of the version history (``/articles/{id}/revisions``)."""

    def __init__(self, db: AsyncSession):
        """Initialize the revisions repository."""

        self.repository = ArticleRevisionRepository(db)

    async def list_revisions(
        self, article_id: int, *, page: int, size: int, cursor: str | None = None, use_cursor: bool = False
    ) -> Page[ArticleRevisionBrief] | CursorPage[ArticleRevisionBrief]:
        """
        History, newest first; 404 if the article doesn't exist. Offset ``Page``, or with ``use_cursor`` a keyset
        ``CursorPage`` over ``version`` (new versions on top never shift it).
        """

        if not await self.repository.article_exists(article_id):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        if use_cursor:
            before = decode_cursor(cursor, CURSOR_SORT).id if cursor is not None else None
            rows, _ = await self.repository.list_for_article(
                article_id, skip=0, limit=size + 1, before_version=before, with_total=False
            )
            rows, next_cursor = cursor_page(rows, size, CURSOR_SORT, lambda row: ("", row.version))
            items = [ArticleRevisionBrief.model_validate(row) for row in rows]
            return CursorPage(items=items, next_cursor=next_cursor, size=size)

        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_for_article(article_id, skip=skip, limit=limit)
        items = [ArticleRevisionBrief.model_validate(row) for row in rows]
        return Page(items=items, total=total or 0, page=page, size=size)

    async def get_revision(self, article_id: int, version: int) -> ArticleRevisionResponse:
        """One full snapshot; 404 if the article has no such version."""

        return ArticleRevisionResponse.model_validate(await self._get_or_404(article_id, version))

    async def diff(self, article_id: int, version: int, against: int | None) -> ArticleRevisionDiff:
        """
        What changed in ``version`` relative to ``against`` (default: the previous version; for version 1 the
        diff is against an empty article).
        """

        new = await self._get_or_404(article_id, version)
        base = version - 1 if against is None else against
        old = await self._get_or_404(article_id, base) if base > 0 else None
        return build_diff(old, new)

    async def _get_or_404(self, article_id: int, version: int) -> ArticleRevision:
        revision = await self.repository.get(article_id, version)
        if revision is None:
            raise RecordNotFoundError(model_name="ArticleRevision", model_id=f"{article_id}@{version}")

        return revision
