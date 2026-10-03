"""
Article write queries (content UPDATE, version + revision snapshot, slug allocation, delete) and the detail lookups.

Tree writes/reads live in ``tree.repository``, listing/search in ``listing.repository``, status moves in
``workflow.repository``.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from sqlalchemy import and_, delete, insert, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Executable

from app.core.exceptions import RecordAlreadyExistsError
from app.features.articles.base import ArticleScopedRepository
from app.features.articles.revisions.hashing import revision_hash
from app.features.articles.slug import slugify
from app.features.articles.visibility import visibility_conditions
from app.models.articles.article_image_model import ArticleImage
from app.models.articles.article_model import Article
from app.models.articles.article_revision_model import ArticleRevision
from app.models.articles.article_subtype_model import ArticleSubtype

T = TypeVar("T")

#: Content fields: a change to any of them is a new version (mirrored in ``ArticleRevision``).
REVISED_FIELDS = ("title", "excerpt", "body_markdown", "article_type", "subtype_id", "visibility")

#: Tries at a free slug before giving up when concurrent writers keep taking the candidate.
SLUG_ATTEMPTS = 5


class ArticleRepository(ArticleScopedRepository):
    """
    Article rows with eager-loaded tags and images (``get_by_id`` serializes a full ``ArticleResponse``).

    No ``check_in_use_on_delete``: deleting an article that's someone's ``parent_id`` just detaches its children
    (``ondelete="SET NULL"`` + ``ArticleTreeRepository.detach_children``); nothing downstream depends on an article.
    """

    def __init__(self, db: AsyncSession):
        """Initialize with eager-loaded tags and images, searchable by title/slug, unique slug."""

        super().__init__(db, load_tags_and_images=True, search_fields=["title", "slug"], unique_fields=["slug"])

    async def update_fields(self, article_id: int, fields: dict, *, commit: bool = True) -> None:
        """
        Write ``fields`` onto the article with one UPDATE, committing or flushing.

        No slug pre-check: a slug only arrives from ``write_with_unique_slug``, which picked a free one and retries
        on the unique constraint's ``IntegrityError`` if a concurrent writer took it meanwhile.
        """

        if fields:
            await self.db.execute(
                update(Article)
                .where(Article.id == article_id)
                .values(**fields)
                .execution_options(synchronize_session=False)
            )

        await self.commit_or_flush(commit=commit)

    async def lock_version(self, article_id: int) -> int | None:
        """Lock the article row until the transaction ends and return its current ``version`` (``None`` if absent)."""

        return await self.db.scalar(select(Article.version).where(Article.id == article_id).with_for_update())

    async def record_revision(
        self,
        article_id: int,
        *,
        editor_id: int | None,
        reviewer_id: int | None,
        change_note: str | None,
        bump: bool,
    ) -> int:
        """
        Snapshot the article's current content into ``article_revisions`` and return the new version.

        ``bump=True`` increments ``articles.version`` and reads the snapshot back in the same ``UPDATE … RETURNING``
        (call it after the content UPDATE, which holds the row lock, so concurrent saves get distinct versions).
        A new article is recorded with ``bump=False`` (its first version is the column default, 1). The snapshot
        is what was actually stored, whatever the service normalized; its ``content_hash`` chains to the previous
        version's (see ``revision_hash``).
        """

        columns = (Article.version, *(getattr(Article, field) for field in REVISED_FIELDS))
        stmt: Executable
        if bump:
            stmt = (
                update(Article)
                .where(Article.id == article_id)
                .values(version=Article.version + 1)
                .returning(*columns)
                .execution_options(synchronize_session=False)
            )
        else:
            stmt = select(*columns).where(Article.id == article_id)
        row = (await self.db.execute(stmt)).one()
        content = {field: getattr(row, field) for field in REVISED_FIELDS}
        parent_hash = await self.db.scalar(
            select(ArticleRevision.content_hash).where(
                ArticleRevision.article_id == article_id, ArticleRevision.version == row.version - 1
            )
        )
        await self.db.execute(
            insert(ArticleRevision).values(
                article_id=article_id,
                version=row.version,
                **content,
                editor_id=editor_id,
                reviewer_id=reviewer_id,
                change_note=change_note,
                content_hash=revision_hash(parent_hash, row.version, content),
            )
        )
        return row.version

    async def delete_row(self, article_id: int) -> bool:
        """Delete the article row with one statement (tags, relations and images go with it by FK cascade)."""

        result = await self.db.execute(
            delete(Article).where(Article.id == article_id).execution_options(synchronize_session=False)
        )
        return bool(cast(CursorResult[Any], result).rowcount)

    async def generate_unique_slug(self, title: str, *, exclude_id: int | None = None) -> str:
        """
        Build a slug from ``title`` that no article uses yet: ``base``, then ``base-2``, ``base-3``, ...

        ``exclude_id`` ignores that article's own current slug (re-slugging on rename). Concurrent writers can
        still pick the same value; ``write_with_unique_slug`` retries on that.
        """

        base = slugify(title)
        stmt = select(Article.slug).where(or_(Article.slug == base, Article.slug.like(f"{base}-%")))
        if exclude_id is not None:
            stmt = stmt.where(Article.id != exclude_id)
        taken = set((await self.db.execute(stmt)).scalars().all())

        candidate, suffix = base, 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"
            suffix += 1

        return candidate

    async def write_with_unique_slug(
        self, title: str, write: Callable[[str], Awaitable[T]], *, exclude_id: int | None = None
    ) -> T:
        """
        Run ``write(slug)`` with a free slug, retrying with a fresh one when a concurrent writer took it first.

        Each attempt runs in its own savepoint, so a lost race rolls back only that attempt and the enclosing
        transaction stays usable. ``write`` must flush so the unique constraint fires here.

        Raises:
            RecordAlreadyExistsError: still no free slug after ``SLUG_ATTEMPTS`` tries.
        """

        slug = ""
        for _ in range(SLUG_ATTEMPTS):
            slug = await self.generate_unique_slug(title, exclude_id=exclude_id)
            try:
                async with self.db.begin_nested():
                    return await write(slug)
            except RecordAlreadyExistsError:
                continue
            except IntegrityError as exc:
                if "slug" not in str(exc.orig).lower():
                    raise

        raise RecordAlreadyExistsError(model_name="Article", field="slug", value=slug)

    async def get_id_by_slug(self, slug: str) -> int | None:
        """The id of the article with this ``slug`` (any visibility), or ``None``."""

        return await self.db.scalar(select(Article.id).where(Article.slug == slug))

    async def get_public_state(self, *, article_id: int | None = None, slug: str | None = None) -> Any:
        """
        One query for a non-GM detail read, by ``article_id`` or ``slug``: ``(id, visible_parent_id)`` if the
        article is published and public, else ``None``.

        ``visible_parent_id`` is the parent's id only when that parent is visible too (``None`` otherwise), so a
        hidden parent's id never reaches the reader.
        """

        parent = aliased(Article)
        stmt = (
            select(Article.id, parent.id.label("visible_parent_id"))
            .outerjoin(parent, and_(parent.id == Article.parent_id, *visibility_conditions(False, parent)))
            .where(Article.id == article_id if slug is None else Article.slug == slug, *visibility_conditions(False))
        )
        return (await self.db.execute(stmt)).one_or_none()

    async def get_subtype_type(self, subtype_id: int) -> str | None:
        """The ``article_type`` a subtype belongs to, or ``None`` if it doesn't exist."""

        return await self.db.scalar(select(ArticleSubtype.article_type).where(ArticleSubtype.id == subtype_id))

    async def list_image_keys(self, article_id: int) -> list[tuple[int, str]]:
        """``(id, storage_key)`` of every image owned by the article (for storage cleanup on delete)."""

        result = await self.db.execute(
            select(ArticleImage.id, ArticleImage.storage_key).where(ArticleImage.article_id == article_id)
        )
        return [(row.id, row.storage_key) for row in result]
