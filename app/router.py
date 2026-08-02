from fastapi import APIRouter

from app.features.auth.endpoints import router as auth_router
from app.features.backgrounds.endpoints import router as background_router

from app.features.characters.router import router as character_router
from app.features.classes.endpoints import router as class_router
from app.features.feats.endpoints import router as feat_router
from app.features.features.endpoints import router as feature_router
from app.features.items.endpoints import router as item_router
from app.features.ping.endpoints import router as ping_router
from app.features.races.endpoints import router as race_router
from app.features.skills.endpoints import router as skill_router
from app.features.spells.endpoints import router as spell_router
from app.features.users.endpoints import router as user_router

api_router = APIRouter(prefix="/api")

_feature_routers = (
    ping_router,
    auth_router,
    user_router,
    race_router,
    class_router,
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
