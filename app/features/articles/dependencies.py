"""Per-capability dependency providers for the articles domain (one ``Article*Dep`` per service)."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.core.storage.dependencies import StorageServiceDep
from app.features.articles.crud.service import ArticleCrudService
from app.features.articles.images.service import ArticleImagesService
from app.features.articles.listing.service import ArticleListingService
from app.features.articles.proposals.service import ArticleProposalsService
from app.features.articles.relations.service import ArticleRelationsService
from app.features.articles.revisions.service import ArticleRevisionsService
from app.features.articles.subtypes.service import ArticleSubtypeService
from app.features.articles.tags.service import ArticleTagService
from app.features.articles.tree.service import ArticleTreeService
from app.features.articles.workflow.service import ArticleWorkflowService


def get_article_crud_service(db: DatabaseDep, storage: StorageServiceDep) -> ArticleCrudService:
    """Article CRUD + detail reads (needs storage to clean up images on delete)."""

    return ArticleCrudService(db, storage)


ArticleCrudDep = Annotated[ArticleCrudService, Depends(get_article_crud_service)]


def get_article_listing_service(db: DatabaseDep) -> ArticleListingService:
    """``GET /articles`` and ``/articles/search``."""

    return ArticleListingService(db)


ArticleListingDep = Annotated[ArticleListingService, Depends(get_article_listing_service)]


def get_article_tree_service(db: DatabaseDep) -> ArticleTreeService:
    """Children / descendants / ancestors reads."""

    return ArticleTreeService(db)


ArticleTreeDep = Annotated[ArticleTreeService, Depends(get_article_tree_service)]


def get_article_workflow_service(db: DatabaseDep) -> ArticleWorkflowService:
    """Review-workflow status moves."""

    return ArticleWorkflowService(db)


ArticleWorkflowDep = Annotated[ArticleWorkflowService, Depends(get_article_workflow_service)]


def get_article_tag_service(db: DatabaseDep) -> ArticleTagService:
    """Full replacement of an article's tags."""

    return ArticleTagService(db)


ArticleTagsDep = Annotated[ArticleTagService, Depends(get_article_tag_service)]


def get_article_relations_service(db: DatabaseDep) -> ArticleRelationsService:
    """The article relation graph."""

    return ArticleRelationsService(db)


ArticleRelationsDep = Annotated[ArticleRelationsService, Depends(get_article_relations_service)]


def get_article_images_service(db: DatabaseDep, storage: StorageServiceDep) -> ArticleImagesService:
    """Article image upload / list / delete."""

    return ArticleImagesService(db, storage)


ArticleImagesDep = Annotated[ArticleImagesService, Depends(get_article_images_service)]


def get_article_subtype_service(db: DatabaseDep) -> ArticleSubtypeService:
    """The GM-managed subtype dictionary."""

    return ArticleSubtypeService(db)


ArticleSubtypesDep = Annotated[ArticleSubtypeService, Depends(get_article_subtype_service)]


def get_article_revisions_service(db: DatabaseDep) -> ArticleRevisionsService:
    """Version history reads."""

    return ArticleRevisionsService(db)


ArticleRevisionsDep = Annotated[ArticleRevisionsService, Depends(get_article_revisions_service)]


def get_article_proposals_service(db: DatabaseDep) -> ArticleProposalsService:
    """Change proposals (writes accepted ones through its own ``ArticleWriter``; no storage needed)."""

    return ArticleProposalsService(db)


ArticleProposalsDep = Annotated[ArticleProposalsService, Depends(get_article_proposals_service)]
