"""Article subtype endpoints: list, create, rename, delete."""

from fastapi import APIRouter, Query, status

from app.features.articles.dependencies import ArticleSubtypesDep
from app.features.articles.subtypes.schemas import (
    ArticleSubtypeCreate,
    ArticleSubtypeResponse,
    ArticleSubtypeUpdate,
)
from app.features.auth.dependencies import FounderDep, GmUserDep

router = APIRouter()


@router.get("", response_model=list[ArticleSubtypeResponse], summary="List article subtypes")
async def get_subtypes(
    subtype_service: ArticleSubtypesDep,
    article_type: str | None = Query(None, description="Only subtypes of this article_type (for the editor picker)."),
):
    """Return every subtype, ordered by `article_type` then name. Open endpoint."""

    return await subtype_service.list_subtypes(article_type)


@router.post(
    "",
    response_model=ArticleSubtypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an article subtype",
    responses={400: {"description": "This article_type already has a subtype with this name (case-insensitive)."}},
)
async def create_subtype(data: ArticleSubtypeCreate, subtype_service: ArticleSubtypesDep, _: GmUserDep):
    """Add a subtype to one `article_type` (fixed for good). **GM only.**"""

    return await subtype_service.create(data)


@router.patch(
    "/{subtype_id:int}",
    response_model=ArticleSubtypeResponse,
    summary="Rename an article subtype",
    responses={
        400: {"description": "The type already has a subtype with this name."},
        404: {"description": "No subtype exists with the given ID."},
    },
)
async def update_subtype(
    subtype_id: int, data: ArticleSubtypeUpdate, subtype_service: ArticleSubtypesDep, _: GmUserDep
):
    """Rename a subtype; every article using it shows the new name. **GM only.**"""

    return await subtype_service.update(subtype_id, data)


@router.delete(
    "/{subtype_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an article subtype",
    responses={404: {"description": "No subtype exists with the given ID."}},
)
async def delete_subtype(subtype_id: int, subtype_service: ArticleSubtypesDep, _: FounderDep):
    """Delete a subtype; articles using it are left without one. **Founder only.**"""

    await subtype_service.delete(subtype_id)
