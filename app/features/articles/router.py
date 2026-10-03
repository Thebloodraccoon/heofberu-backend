"""Assembled ``/articles`` router: one ``include_router`` per capability (see ``README.md`` for the map)."""

from fastapi import APIRouter

from app.features.articles.crud.router import router as crud_router
from app.features.articles.images.router import router as images_router
from app.features.articles.listing.router import router as listing_router
from app.features.articles.proposals.router import queue_router as proposals_queue_router
from app.features.articles.proposals.router import router as proposals_router
from app.features.articles.relations.router import router as relations_router
from app.features.articles.revisions.router import router as revisions_router
from app.features.articles.subtypes.router import router as subtypes_router
from app.features.articles.tags.router import router as tags_router
from app.features.articles.tree.router import router as tree_router
from app.features.articles.workflow.router import router as workflow_router

router = APIRouter()

router.include_router(listing_router, prefix="/articles", tags=["Articles"])
router.include_router(crud_router, prefix="/articles", tags=["Articles"])
router.include_router(tree_router, prefix="/articles", tags=["Articles"])
router.include_router(workflow_router, prefix="/articles", tags=["Articles"])
router.include_router(proposals_queue_router, prefix="/articles", tags=["Articles Proposals"])
router.include_router(tags_router, prefix="/articles", tags=["Articles"])
router.include_router(subtypes_router, prefix="/articles/subtypes", tags=["Articles Subtypes"])
router.include_router(relations_router, prefix="/articles/{article_id}", tags=["Articles Relations"])
router.include_router(images_router, prefix="/articles/{article_id}", tags=["Articles Images"])
router.include_router(revisions_router, prefix="/articles/{article_id}", tags=["Articles Revisions"])
router.include_router(proposals_router, prefix="/articles/{article_id}", tags=["Articles Proposals"])
