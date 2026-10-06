"""Per-capability dependency providers for the backgrounds domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.backgrounds.crud.service import BackgroundCrudService
from app.features.backgrounds.features.service import BackgroundFeatureService
from app.features.backgrounds.items.service import BackgroundItemsService
from app.features.backgrounds.skills.service import BackgroundSkillsService
from app.features.backgrounds.suggestions.service import BackgroundSuggestionsService
from app.features.backgrounds.tags.service import BackgroundTagService


def get_background_crud_service(db: DatabaseDep) -> BackgroundCrudService:
    """Get the background CRUD service instance."""

    return BackgroundCrudService(db)


BackgroundCrudDep = Annotated[BackgroundCrudService, Depends(get_background_crud_service)]


def get_background_feature_service(db: DatabaseDep) -> BackgroundFeatureService:
    """Get the background feature service instance."""

    return BackgroundFeatureService(db)


BackgroundFeaturesDep = Annotated[BackgroundFeatureService, Depends(get_background_feature_service)]


def get_background_skill_service(db: DatabaseDep) -> BackgroundSkillsService:
    """Get the background skills service instance."""

    return BackgroundSkillsService(db)


BackgroundSkillsDep = Annotated[BackgroundSkillsService, Depends(get_background_skill_service)]


def get_background_item_service(db: DatabaseDep) -> BackgroundItemsService:
    """Get the background items service instance."""

    return BackgroundItemsService(db)


BackgroundItemsDep = Annotated[BackgroundItemsService, Depends(get_background_item_service)]


def get_background_suggestions_service(db: DatabaseDep) -> BackgroundSuggestionsService:
    """Get the background suggestions service instance."""

    return BackgroundSuggestionsService(db)


BackgroundSuggestionsDep = Annotated[BackgroundSuggestionsService, Depends(get_background_suggestions_service)]


def get_background_tag_service(db: DatabaseDep) -> BackgroundTagService:
    """Get the background tags service instance."""

    return BackgroundTagService(db)


BackgroundTagsDep = Annotated[BackgroundTagService, Depends(get_background_tag_service)]
