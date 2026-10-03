"""Article relations repository: per-article combined listing and per-relation CRUD."""

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only, noload

from app.constants import ArticleVisibility
from app.features.articles.base import ArticleScopedRepository
from app.features.articles.relations.schemas import ArticleRelationCreate
from app.features.articles.visibility import visibility_conditions
from app.models.articles.article_model import Article
from app.models.articles.article_relation_model import ArticleRelation

#: Cap on the unpaginated relation list, so a hub article can't return its whole graph.
RELATIONS_LIMIT = 500


class ArticleRelationsRepository(ArticleScopedRepository):
    """Relation persistence for articles (the article lookups come from :class:`ArticleScopedRepository`)."""

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` without the tags/images eager loads (relations never serialize them)."""

        super().__init__(db)

    async def list_relations(self, article_id: int, *, include_hidden: bool) -> list[tuple[ArticleRelation, Article]]:
        """
        Return the relations touching the article (either direction) as ``(relation, far-side article)`` pairs,
        newest first, at most ``RELATIONS_LIMIT``.

        One query: only the far side is joined (the near side is the article itself). For non-GM readers
        (``include_hidden=False``) GM-only relations and relations whose far side isn't a published, public
        article are filtered out in SQL.
        """

        other = aliased(Article)
        other_id = case(
            (ArticleRelation.from_article_id == article_id, ArticleRelation.to_article_id),
            else_=ArticleRelation.from_article_id,
        )
        conditions = [or_(ArticleRelation.from_article_id == article_id, ArticleRelation.to_article_id == article_id)]
        if not include_hidden:
            conditions += [ArticleRelation.visibility == ArticleVisibility.PUBLIC, *visibility_conditions(False, other)]

        result = await self.db.execute(
            select(ArticleRelation, other)
            .join(other, other.id == other_id)
            .where(*conditions)
            .options(
                load_only(other.id, other.slug, other.title, other.article_type, other.subtype_id),
                noload(other.author),  # joined by default; an ``ArticleBrief`` has no author
            )
            .order_by(ArticleRelation.created_at.desc(), ArticleRelation.id.desc())
            .limit(RELATIONS_LIMIT)
        )
        return [(relation, far_side) for relation, far_side in result.all()]

    async def get_relation(self, article_id: int, relation_id: int) -> ArticleRelation | None:
        """Fetch a single relation scoped to the article (either direction), or ``None``."""

        result = await self.db.execute(
            select(ArticleRelation).where(
                ArticleRelation.id == relation_id,
                or_(ArticleRelation.from_article_id == article_id, ArticleRelation.to_article_id == article_id),
            )
        )
        return result.scalar_one_or_none()

    async def create_relation(
        self, article_id: int, data: ArticleRelationCreate, *, commit: bool = True
    ) -> ArticleRelation:
        """Link ``article_id`` (source) to ``data.to_article_id`` (target)."""

        row = ArticleRelation(
            from_article_id=article_id,
            to_article_id=data.to_article_id,
            relation_type=data.relation_type,
            note=data.note,
            visibility=data.visibility,
        )
        self.db.add(row)
        await self.commit_or_flush(commit=commit)
        await self.db.refresh(row, attribute_names=["from_article", "to_article"])

        return row

    async def update_relation(self, relation: ArticleRelation, fields: dict, *, commit: bool = True) -> ArticleRelation:
        """Apply ``fields`` (relation_type/note/visibility) to an existing relation."""

        for field, value in fields.items():
            setattr(relation, field, value)

        await self.commit_or_flush(commit=commit)
        await self.db.refresh(relation, attribute_names=["from_article", "to_article"])

        return relation

    async def delete_relation(self, relation: ArticleRelation, *, commit: bool = True) -> None:
        """Remove a single relation."""

        await self.db.delete(relation)
        await self.commit_or_flush(commit=commit)
