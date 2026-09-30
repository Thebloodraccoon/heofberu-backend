"""Assembled ``/articles`` router."""

from fastapi import APIRouter

from app.features.articles.crud.router import router as crud_router
from app.features.articles.images.router import router as images_router
from app.features.articles.relations.router import router as relations_router
from app.features.articles.subtypes.router import router as subtypes_router
from app.features.articles.tags.router import router as tags_router

router = APIRouter()

router.include_router(crud_router, prefix="/articles", tags=["Articles"])
router.include_router(tags_router, prefix="/articles", tags=["Articles"])
router.include_router(subtypes_router, prefix="/articles/subtypes", tags=["Articles Subtypes"])
router.include_router(relations_router, prefix="/articles/{article_id}", tags=["Articles Relations"])
router.include_router(images_router, prefix="/articles/{article_id}", tags=["Articles Images"])
