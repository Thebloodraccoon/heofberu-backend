"""Article tag endpoints: full replacement of an article's tags."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.articles.crud.schemas import ArticleResponse
from app.features.articles.dependencies import ArticleTagsDep
from app.features.shared.tags.schemas import TagsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{article_id:int}/tags",
    response_model=ArticleResponse,
    summary="Replace an article's tags",
    responses={
        400: {"description": "One or more tag IDs don't correspond to an existing tag."},
        404: {"description": "No article exists with the given ID."},
    },
)
async def set_tags(
    article_id: int,
    data: Annotated[
        TagsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two tags",
                    "value": {"tag_ids": [3, 7]},
                },
                "clear": {
                    "summary": "Clear all tags",
                    "value": {"tag_ids": []},
                },
            },
        ),
    ],
    article_service: ArticleTagsDep,
    _: GmUserDep,
):
    """Replace all tags for an article, from the shared tag dictionary. **GM only.**"""

    return await article_service.set_tags(article_id, data)
