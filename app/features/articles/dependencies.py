"""Per-capability dependency providers for the articles domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.core.storage.dependencies import StorageServiceDep
from app.features.articles.crud.service import ArticleCrudService
from app.features.articles.images.service import ArticleImagesService
from app.features.articles.relations.service import ArticleRelationsService
from app.features.articles.tags.service import ArticleTagService


def get_article_crud_service(db: DatabaseDep, storage: StorageServiceDep) -> ArticleCrudService:
    """Get the article CRUD service instance."""

    return ArticleCrudService(db, storage)


ArticleCrudDep = Annotated[ArticleCrudService, Depends(get_article_crud_service)]


def get_article_tag_service(db: DatabaseDep) -> ArticleTagService:
    """Get the article tags service instance."""

    return ArticleTagService(db)


ArticleTagsDep = Annotated[ArticleTagService, Depends(get_article_tag_service)]


def get_article_relations_service(db: DatabaseDep) -> ArticleRelationsService:
    """Get the article relations service instance."""

    return ArticleRelationsService(db)


ArticleRelationsDep = Annotated[ArticleRelationsService, Depends(get_article_relations_service)]


def get_article_images_service(db: DatabaseDep, storage: StorageServiceDep) -> ArticleImagesService:
    """Get the article images service instance."""

    return ArticleImagesService(db, storage)


ArticleImagesDep = Annotated[ArticleImagesService, Depends(get_article_images_service)]
