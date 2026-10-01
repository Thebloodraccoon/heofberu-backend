"""Article relations service: combined listing plus per-relation create/delete."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import use_cache
from app.core.exceptions import RecordAlreadyExistsError, RecordIdsInvalidError, RecordNotFoundError
from app.features.articles.base import ArticleScopedService
from app.features.articles.cache import ARTICLE_TREE_NAMESPACE, invalidate_article_trees
from app.features.articles.crud.schemas import ArticleBrief
from app.features.articles.relations.exceptions import ArticleRelationNotFoundException, ArticleSelfRelationException
from app.features.articles.relations.repository import ArticleRelationsRepository
from app.features.articles.relations.schemas import (
    ArticleRelationCreate,
    ArticleRelationResponse,
    ArticleRelationUpdate,
)
from app.features.articles.secrets import strip_gm_blocks
from app.models.articles.article_relation_model import ArticleRelation


class ArticleRelationsService(ArticleScopedService):
    """
    Article relation graph: combined incoming+outgoing listing plus
    per-relation create/delete (everything that doesn't fit the
    ``parent_id``/``path`` hierarchy — membership, kinship, feud, mentions).
    """

    repository: ArticleRelationsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the service with the relations repository."""

        super().__init__(ArticleRelationsRepository(db))

    async def list_relations(self, article_id: int, *, include_hidden: bool) -> list[ArticleRelationResponse]:
        """
        Return the relations touching the article, from the article's point of view.

        For non-GM readers the article itself must be visible, and GM-only relations plus
        relations pointing at a draft/GM-only article are dropped (so their existence isn't leaked).
        """

        if not await self.repository.exists_visible(article_id, include_hidden):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        return await self._cached_relations(article_id, include_hidden=include_hidden)

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_relations(self, article_id: int, *, include_hidden: bool) -> list[ArticleRelationResponse]:
        rows = await self.repository.list_relations(article_id, include_hidden=include_hidden)
        return [self._to_response(article_id, row, strip_secrets=not include_hidden) for row in rows]

    async def create_relation(self, article_id: int, data: ArticleRelationCreate) -> ArticleRelationResponse:
        """Link ``article_id`` to ``data.to_article_id``. Both ids must already exist."""

        await self._exists_or_404(article_id)

        if data.to_article_id == article_id:
            raise ArticleSelfRelationException(article_id=article_id)

        if not await self.repository.exists_by_id(data.to_article_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[data.to_article_id])

        if await self.repository.relation_exists(article_id, data.to_article_id, data.relation_type):
            raise RecordAlreadyExistsError(
                model_name="ArticleRelation",
                field="relation_type",
                value=f"{article_id} -[{data.relation_type}]-> {data.to_article_id}",
            )

        row = await self.repository.create_relation(article_id, data)
        await invalidate_article_trees(self.repository.db)

        return self._to_response(article_id, row)

    async def update_relation(
        self, article_id: int, relation_id: int, data: ArticleRelationUpdate
    ) -> ArticleRelationResponse:
        """Change a relation's type/note/visibility; either end of it may be the path article."""

        await self._exists_or_404(article_id)
        relation = await self._get_relation_or_404(article_id, relation_id)
        fields = data.model_dump(exclude_unset=True)

        new_type = fields.get("relation_type")
        if new_type is not None and new_type != relation.relation_type:
            if await self.repository.relation_exists(
                relation.from_article_id, relation.to_article_id, new_type, exclude_id=relation.id
            ):
                raise RecordAlreadyExistsError(
                    model_name="ArticleRelation",
                    field="relation_type",
                    value=f"{relation.from_article_id} -[{new_type}]-> {relation.to_article_id}",
                )

        updated = await self.repository.update_relation(relation, fields)
        await invalidate_article_trees(self.repository.db)

        return self._to_response(article_id, updated)

    async def delete_relation(self, article_id: int, relation_id: int) -> None:
        """Remove a single relation touching the article (either direction)."""

        await self._exists_or_404(article_id)
        relation = await self._get_relation_or_404(article_id, relation_id)
        await self.repository.delete_relation(relation)
        await invalidate_article_trees(self.repository.db)

    async def _get_relation_or_404(self, article_id: int, relation_id: int) -> ArticleRelation:
        """Fetch a relation scoped to the article, or raise ``ArticleRelationNotFoundException``."""

        relation = await self.repository.get_relation(article_id, relation_id)
        if not relation:
            raise ArticleRelationNotFoundException(article_id=article_id, relation_id=relation_id)

        return relation

    @staticmethod
    def _to_response(
        article_id: int, relation: ArticleRelation, *, strip_secrets: bool = False
    ) -> ArticleRelationResponse:
        """Direction-aware response for ``relation`` as seen from ``article_id``; ``strip_secrets`` cuts ``:::gm``."""

        outgoing = relation.from_article_id == article_id
        other = relation.to_article if outgoing else relation.from_article

        return ArticleRelationResponse(
            id=relation.id,
            relation_type=relation.relation_type,
            note=strip_gm_blocks(relation.note) if strip_secrets else relation.note,
            visibility=relation.visibility,
            created_at=relation.created_at,
            direction="outgoing" if outgoing else "incoming",
            article=ArticleBrief.model_validate(other),
        )
