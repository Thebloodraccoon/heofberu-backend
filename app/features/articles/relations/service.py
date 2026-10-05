"""Article relations: the combined incoming+outgoing listing (cached per end) and per-relation create/update/delete."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import invalidate_after_commit
from app.core.cache import build_cache_key, use_cache
from app.core.db_errors import constraint_name
from app.core.exceptions import RecordAlreadyExistsError, RecordIdsInvalidError, RecordNotFoundError
from app.features.articles.base import ArticleScopedService
from app.features.articles.cache import ARTICLE_TREE_NAMESPACE
from app.features.articles.crud.schemas import ArticleBrief
from app.features.articles.relations.exceptions import ArticleRelationNotFoundException, ArticleSelfRelationException
from app.features.articles.relations.repository import ArticleRelationsRepository
from app.features.articles.relations.schemas import (
    ArticleRelationCreate,
    ArticleRelationResponse,
    ArticleRelationUpdate,
)
from app.features.articles.secrets import strip_gm_blocks
from app.models.articles.article_model import Article
from app.models.articles.article_relation_model import ArticleRelation

#: ``(from_article_id, to_article_id, relation_type)`` unique constraint on ``article_relations``.
UNIQUE_RELATION_CONSTRAINT = "uq_article_relation"


def relations_cache_key(article_id: int, include_hidden: bool) -> str:
    """Exact key of ``ArticleRelationsService._cached_relations`` for one article and reader kind."""

    return build_cache_key(
        ArticleRelationsService._cached_relations,
        None,
        article_id,
        include_hidden=include_hidden,
        namespace=ARTICLE_TREE_NAMESPACE,
    )


async def invalidate_relations(db: AsyncSession, *article_ids: int) -> None:
    """Drop these articles' cached relation lists (GM and reader variants); a relation is listed from both ends."""

    keys = [relations_cache_key(article_id, hidden) for article_id in article_ids for hidden in (True, False)]
    await invalidate_after_commit(db, keys=keys)


def _raise_if_duplicate(exc: IntegrityError, from_id: int, to_id: int, relation_type: str) -> None:
    """Turn a ``uq_article_relation`` violation into ``RecordAlreadyExistsError``; any other error is left alone."""

    if constraint_name(exc) == UNIQUE_RELATION_CONSTRAINT:
        raise RecordAlreadyExistsError(
            model_name="ArticleRelation", field="relation_type", value=f"{from_id} -[{relation_type}]-> {to_id}"
        ) from exc


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
        """Cached body of ``list_relations``; key ``relations_cache_key(article_id, include_hidden)``."""

        rows = await self.repository.list_relations(article_id, include_hidden=include_hidden)
        return [
            self._to_response(article_id, relation, other, strip_secrets=not include_hidden) for relation, other in rows
        ]

    async def create_relation(self, article_id: int, data: ArticleRelationCreate) -> ArticleRelationResponse:
        """
        Link ``article_id`` (source) to ``data.to_article_id`` (target) and return the relation as seen from the source.

        Raises:
            RecordNotFoundError: the source article doesn't exist.
            ArticleSelfRelationException: source and target are the same article (400).
            RecordIdsInvalidError: the target doesn't exist (400).
            RecordAlreadyExistsError: this ``(from, to, relation_type)`` already exists (caught from
                ``uq_article_relation``, so two concurrent creates can't both pass a pre-check).
        """

        await self._exists_or_404(article_id)

        if data.to_article_id == article_id:
            raise ArticleSelfRelationException(article_id=article_id)

        if not await self.repository.exists_by_id(data.to_article_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[data.to_article_id])

        try:
            async with self._atomic():
                row = await self.repository.create_relation(article_id, data)
                await invalidate_relations(self.repository.db, article_id, data.to_article_id)
        except IntegrityError as exc:
            _raise_if_duplicate(exc, article_id, data.to_article_id, data.relation_type)
            raise

        return self._to_response(article_id, row)

    async def update_relation(
        self, article_id: int, relation_id: int, data: ArticleRelationUpdate
    ) -> ArticleRelationResponse:
        """
        Change a relation's type/note/visibility (PATCH semantics); either end may be the path article.

        Raises:
            RecordNotFoundError / ArticleRelationNotFoundException: no such article / relation on it.
            RecordAlreadyExistsError: the new ``relation_type`` duplicates another relation between the same ends.
        """

        await self._exists_or_404(article_id)
        relation = await self._get_relation_or_404(article_id, relation_id)
        from_id, to_id = relation.from_article_id, relation.to_article_id
        fields = data.model_dump(exclude_unset=True)

        try:
            async with self._atomic():
                updated = await self.repository.update_relation(relation, fields)
                await invalidate_relations(self.repository.db, from_id, to_id)
        except IntegrityError as exc:
            _raise_if_duplicate(exc, from_id, to_id, fields.get("relation_type", ""))
            raise

        return self._to_response(article_id, updated)

    async def delete_relation(self, article_id: int, relation_id: int) -> None:
        """Remove a single relation touching the article (either direction); 404 if it isn't on this article."""

        await self._exists_or_404(article_id)
        relation = await self._get_relation_or_404(article_id, relation_id)
        from_id, to_id = relation.from_article_id, relation.to_article_id

        async with self._atomic():
            await self.repository.delete_relation(relation)
            await invalidate_relations(self.repository.db, from_id, to_id)

    async def _get_relation_or_404(self, article_id: int, relation_id: int) -> ArticleRelation:
        """Fetch a relation scoped to the article, or raise ``ArticleRelationNotFoundException``."""

        relation = await self.repository.get_relation(article_id, relation_id)
        if not relation:
            raise ArticleRelationNotFoundException(article_id=article_id, relation_id=relation_id)

        return relation

    @staticmethod
    def _to_response(
        article_id: int, relation: ArticleRelation, other: Article | None = None, *, strip_secrets: bool = False
    ) -> ArticleRelationResponse:
        """
        Direction-aware response for ``relation`` as seen from ``article_id``; ``strip_secrets`` cuts ``:::gm``.

        ``other`` is the far-side article when the caller already has it (the listing); otherwise it is taken from
        the relation's loaded ``from_article``/``to_article``.
        """

        outgoing = relation.from_article_id == article_id
        if other is None:
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
