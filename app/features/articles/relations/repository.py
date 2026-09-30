"""Article relations repository: per-article combined listing and per-relation CRUD."""

from sqlalchemy import or_, select
from sqlalchemy.orm import load_only, selectinload

from app.features.articles.crud.repository import ArticleRepository
from app.features.articles.relations.schemas import ArticleRelationCreate
from app.models.articles.article_model import Article
from app.models.articles.article_relation_model import ArticleRelation


class ArticleRelationsRepository(ArticleRepository):
    """Relation persistence for articles, layered on :class:`ArticleRepository`."""

    async def relation_exists(
        self, from_article_id: int, to_article_id: int, relation_type: str, *, exclude_id: int | None = None
    ) -> bool:
        """Return whether this exact ``(from, to, relation_type)`` triple already exists (ignoring ``exclude_id``)."""

        stmt = select(ArticleRelation.id).where(
            ArticleRelation.from_article_id == from_article_id,
            ArticleRelation.to_article_id == to_article_id,
            ArticleRelation.relation_type == relation_type,
        )
        if exclude_id is not None:
            stmt = stmt.where(ArticleRelation.id != exclude_id)

        return await self.db.scalar(stmt) is not None

    async def list_relations(self, article_id: int) -> list[ArticleRelation]:
        """Return every relation touching the article (either direction), newest first."""

        # The response and the visibility filter only need these columns, never body_markdown.
        other_side_columns = load_only(
            Article.id, Article.slug, Article.title, Article.article_type, Article.subtype_id,
            Article.status, Article.visibility,
        )
        result = await self.db.execute(
            select(ArticleRelation)
            .where(or_(ArticleRelation.from_article_id == article_id, ArticleRelation.to_article_id == article_id))
            .options(
                selectinload(ArticleRelation.from_article).options(other_side_columns),
                selectinload(ArticleRelation.to_article).options(other_side_columns),
            )
            .order_by(ArticleRelation.created_at.desc())
        )
        return list(result.scalars().all())

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
