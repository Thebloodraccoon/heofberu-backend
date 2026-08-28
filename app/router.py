"""Aggregates all feature routers under the ``/api`` prefix."""

from fastapi import APIRouter

from app.features.admin.router import router as admin_router
from app.features.auth.router import router as auth_router
from app.features.backgrounds.router import router as background_router
from app.features.characters.router import router as character_router
from app.features.classes.router import router as class_router
from app.features.feats.router import router as feat_router
from app.features.features.router import router as feature_router
from app.features.items.router import router as item_router
from app.features.ping.router import router as ping_router
from app.features.races.router import router as race_router
from app.features.skills.router import router as skill_router
from app.features.spells.router import router as spell_router
from app.features.subclasses.router import router as subclass_router
from app.features.subraces.router import router as subrace_router
from app.features.users.router import router as user_router

api_router = APIRouter(prefix="/api")

_feature_routers = (
    admin_router,
    ping_router,
    auth_router,
    user_router,
    race_router,
    subrace_router,
    class_router,
    subclass_router,
    skill_router,
    spell_router,
    background_router,
    feat_router,
    feature_router,
    item_router,
    character_router,
)

for _router in _feature_routers:
    api_router.include_router(_router)
