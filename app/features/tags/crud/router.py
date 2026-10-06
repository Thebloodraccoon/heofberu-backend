"""Tag CRUD endpoints: paginated listing, get, create, update, delete."""

from typing import Annotated, Literal

from fastapi import APIRouter, Body, Query, status

from app.core.pagination import Page
from app.features.auth.dependencies import FounderDep, GmUserDep, OptionalUserDep, can_see_hidden
from app.features.tags.crud.schemas import TagCreate, TagGetAllResponse, TagResponse, TagUpdate
from app.features.tags.dependencies import TagCrudDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[TagGetAllResponse],
    summary="List tags",
)
async def get_tags(
    tag_service: TagCrudDep,
    user: OptionalUserDep,
    search: str | None = Query(
        None,
        max_length=100,
        description="Case-insensitive substring match against the tag's name.",
    ),
    sort: Literal["name", "popular"] = Query("name", description="`name` = A-Z, `popular` = most used first."),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of tags, each with a `usage_count` (how many races, subraces,
    backgrounds and articles carry it). Response is `{items, total, page, size}`.
    Non-GMs only get tags on records they can see (drafts/GM-only articles don't count). Open endpoint.
    """

    return await tag_service.list_tags(
        page=page, size=size, search=search, sort=sort, include_hidden=can_see_hidden(user)
    )


@router.get(
    "/suggest",
    response_model=list[TagGetAllResponse],
    summary="Autocomplete tags",
)
async def suggest_tags(
    tag_service: TagCrudDep,
    user: OptionalUserDep,
    q: str = Query(..., min_length=1, max_length=100, description="What the user has typed so far."),
    limit: int = Query(10, ge=1, le=25, description="Max suggestions to return."),
):
    """
    Return up to `limit` tags whose name contains `q` (case-insensitive) — names starting with
    `q` first, then the most used, then A-Z. For a tag picker's typeahead. Same visibility
    rule as `GET /tags`. Open endpoint.
    """

    return await tag_service.suggest(q, limit, include_hidden=can_see_hidden(user))


@router.get(
    "/{tag_id:int}",
    response_model=TagResponse,
    summary="Get a tag by ID",
    responses={
        404: {"description": "Tag with id not found."},
    },
)
async def get_tag(tag_id: int, tag_service: TagCrudDep, user: OptionalUserDep):
    """Return a single tag by ID. 404 for non-GMs if no record they can see carries it. Open endpoint."""

    return await tag_service.get_tag(tag_id, include_hidden=can_see_hidden(user))


@router.post(
    "",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tag",
    responses={
        409: {"description": "A tag with this name already exists."},
    },
)
async def create_tag(
    data: Annotated[
        TagCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Add a new tag to the dictionary",
                    "value": {"name": "Nordavingar"},
                },
            }
        ),
    ],
    tag_service: TagCrudDep,
    _: GmUserDep,
):
    """
    Create a new tag in the shared dictionary. **GM only.**

    Attaching it to a race/subrace/background/article is a separate step —
    `PUT` its `tags` capability endpoint (e.g. `PUT /races/{id}/tags`) with
    this tag's id included.
    """

    return await tag_service.create(data)


@router.patch(
    "/{tag_id:int}",
    response_model=TagResponse,
    summary="Rename a tag",
    responses={
        404: {"description": "No tag exists with the given ID."},
        409: {"description": "Another tag already uses the requested name."},
    },
)
async def update_tag(
    tag_id: int,
    data: Annotated[
        TagUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the tag",
                    "value": {"name": "Nordavingar (Frozen North)"},
                },
            }
        ),
    ],
    tag_service: TagCrudDep,
    _: GmUserDep,
):
    """
    Rename a tag. **GM only.**

    Renaming is global — every race/subrace/background/article this tag is
    already attached to picks up the new name automatically (same row, no
    re-attachment needed).
    """

    return await tag_service.update(tag_id, data)


@router.delete(
    "/{tag_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tag",
    responses={
        404: {"description": "No tag exists with the given ID."},
        409: {"description": "Tag is still attached to a race, subrace, background, or article."},
    },
)
async def delete_tag(tag_id: int, tag_service: TagCrudDep, _: FounderDep):
    """
    Delete a tag from the dictionary, unless it's still attached somewhere.
    **Founder only.**

    Detach it everywhere first (`PUT .../tags` with it left out of the new
    `tag_ids` list on each catalog record) before deleting it here.
    """

    await tag_service.delete(tag_id)
    return None
