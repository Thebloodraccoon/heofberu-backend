"""
Assembled ``/classes/subclasses`` router (query-style parent ID).

Sub-routers declare no prefix of their own; the static ``/subclasses``
prefix is applied here, and the whole subdomain is mounted onto the
``/classes`` router by ``app.features.classes.router`` — combined,
a path here like ``"/features"`` resolves to
``/classes/subclasses/features?class_id=...&subclass_id=...``. The
owning class is identified by the required ``class_id`` query parameter.
"""

from fastapi import APIRouter

from app.features.classes.subclasses.crud.router import router as crud_router
from app.features.classes.subclasses.features.router import router as features_router

router = APIRouter()

router.include_router(crud_router, prefix="/subclasses")
router.include_router(features_router, prefix="/subclasses")
