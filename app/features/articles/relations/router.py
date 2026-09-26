"""Article relation endpoints (mounted under ``/articles/{article_id}``)."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.articles.dependencies import ArticleRelationsDep
from app.features.articles.relations.schemas import (
    ArticleRelationCreate,
    ArticleRelationResponse,
    ArticleRelationUpdate,
)
from app.features.users.security import GmUserDep, OptionalUserDep, can_see_hidden

router = APIRouter()


@router.get(
    "/relations",
    response_model=list[ArticleRelationResponse],
    summary="List an article's relations",
    responses={404: {"description": "No article exists with the given ID."}},
)
async def list_article_relations(article_id: int, article_service: ArticleRelationsDep, user: OptionalUserDep):
    """
    Return every relation touching the article, in either direction
    (`direction` tells you which). Non-GM readers don't see relations to
    drafts/GM-only articles. Open endpoint.
    """

    return await article_service.list_relations(article_id, include_hidden=can_see_hidden(user))


@router.post(
    "/relations",
    response_model=ArticleRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a relation from this article to another",
    responses={
        400: {
            "description": (
                "to_article_id doesn't exist or equals the article itself, relation_type isn't one of "
                "RELATION_TYPES, or the same (from, to, relation_type) relation already exists."
            )
        },
        404: {"description": "No article exists with the given ID."},
    },
)
async def create_article_relation(
    article_id: int,
    data: Annotated[
        ArticleRelationCreate,
        Body(
            openapi_examples={
                "mentions": {
                    "summary": "This article mentions another",
                    "value": {"to_article_id": 12, "relation_type": "MENTIONS"},
                },
                "located_in": {
                    "summary": "This article is located in another",
                    "value": {"to_article_id": 4, "relation_type": "LOCATED_IN", "note": "Deep beneath the Misty Mountains."},
                },
                "secret_membership": {
                    "summary": "Secret membership, hidden from players",
                    "value": {"to_article_id": 7, "relation_type": "MEMBER_OF", "visibility": "gm_only"},
                },
            },
        ),
    ],
    article_service: ArticleRelationsDep,
    _: GmUserDep,
):
    """Link this article to another with a typed, directed relation. **GM only.**"""

    return await article_service.create_relation(article_id, data)


@router.patch(
    "/relations/{relation_id}",
    response_model=ArticleRelationResponse,
    summary="Edit a relation",
    responses={
        400: {
            "description": (
                "relation_type isn't one of RELATION_TYPES, or the same (from, to, relation_type) relation already exists."
            )
        },
        404: {"description": "No article or relation exists with the given IDs."},
    },
)
async def update_article_relation(
    article_id: int,
    relation_id: int,
    data: Annotated[
        ArticleRelationUpdate,
        Body(
            openapi_examples={
                "retype": {
                    "summary": "Change the relation type and note",
                    "value": {"relation_type": "ENEMY_OF", "note": "Since the siege of 1204."},
                },
                "make_secret": {
                    "summary": "Hide the relation from players",
                    "value": {"visibility": "gm_only"},
                },
            }
        ),
    ],
    article_service: ArticleRelationsDep,
    _: GmUserDep,
):
    """
    Change a relation's type, note or visibility (from either of its articles). **GM only.**

    The linked articles and the direction are fixed — to relink, delete the relation and create a new one.
    """

    return await article_service.update_relation(article_id, relation_id, data)


@router.delete(
    "/relations/{relation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a relation",
    responses={404: {"description": "No article or relation exists with the given IDs."}},
)
async def delete_article_relation(article_id: int, relation_id: int, article_service: ArticleRelationsDep, _: GmUserDep):
    """Remove a single relation touching the article (either direction). **GM only.**"""

    await article_service.delete_relation(article_id, relation_id)
    return None
