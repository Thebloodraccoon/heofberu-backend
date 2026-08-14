"""
Assembled ``/classes/{class_id}/subclasses`` router.

Sub-routers declare no prefix of their own; the prefix is applied here,
and the whole subdomain is mounted onto the ``/classes`` router by
``app.features.classes.router`` — combined, a path here like
``"/{subclass_id}/features"`` resolves to
``/classes/{class_id}/subclasses/{subclass_id}/features``.
"""

from fastapi import APIRouter

from app.features.classes.subclasses.crud.router import router as crud_router
from app.features.classes.subclasses.features.router import router as features_router

router = APIRouter()

router.include_router(crud_router, prefix="/{class_id}/subclasses", tags=["Subclasses"])
router.include_router(features_router, prefix="/{class_id}/subclasses", tags=["Subclasses"])
