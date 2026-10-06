"""Article CRUD endpoints: get by id / slug, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.articles.access import ArticleActor
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.dependencies import ArticleCrudDep
from app.features.auth.dependencies import FounderDep, GmUserDep, OptionalUserDep, can_see_hidden

router = APIRouter()


@router.get(
    "/{article_id:int}",
    response_model=ArticleResponse,
    summary="Get an article by ID",
    responses={
        404: {"description": "Article not found (or not visible to the caller)."},
    },
)
async def get_article(article_id: int, article_service: ArticleCrudDep, user: OptionalUserDep):
    """
    Return a single article by ID, with everything about it: base fields, tags and images.
    Drafts and GM-only articles 404 for non-GMs, and `:::gm ... :::` blocks are stripped from
    `body_markdown` for them. Open endpoint.
    """

    return await article_service.get_article(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/by-slug/{slug}",
    response_model=ArticleResponse,
    summary="Get an article by slug",
    responses={
        404: {"description": "Article not found (or not visible to the caller)."},
    },
)
async def get_article_by_slug(slug: str, article_service: ArticleCrudDep, user: OptionalUserDep):
    """Same as `GET /articles/{article_id}`, looked up by the article's `slug`. Open endpoint."""

    return await article_service.get_article_by_slug(slug, include_hidden=can_see_hidden(user))


@router.post(
    "",
    response_model=ArticleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an article",
    responses={
        400: {"description": "parent_id/subtype_id doesn't exist or the subtype belongs to another article_type."},
    },
)
async def create_article(
    data: Annotated[
        ArticleCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Minimal lore entry",
                    "value": {"title": "Khazad-dum", "article_type": "location"},
                },
                "child_of_region": {
                    "summary": "Location nested under a region",
                    "value": {
                        "title": "Moria",
                        "article_type": "location",
                        "subtype_id": 3,
                        "parent_id": 12,
                        "body_markdown": "A once-great dwarven kingdom...\n\n:::gm\nA Balrog sleeps below.\n:::",
                    },
                },
            },
        ),
    ],
    article_service: ArticleCrudDep,
    gm_user: GmUserDep,
):
    """
    Create a new article. **GM only.**

    Identity/content fields only — `tags` are attached afterwards through
    `PUT /articles/{article_id}/tags`. `slug` is generated from the title (never sent by the client), `status`
    starts at `DRAFT`, `author_id` is the calling GM, and `path` is derived server-side from `parent_id`.

    The title is trimmed and may not be blank. A `:::gm` block in `excerpt`/`body_markdown` must be flat: it
    may not contain another `:::` container (422); close it with `:::` first.
    """

    return await article_service.create_article(data, gm_user.id)


@router.patch(
    "/{article_id:int}",
    response_model=ArticleResponse,
    summary="Update an article's fields",
    responses={
        400: {
            "description": "parent_id doesn't exist, would make the article its own ancestor or nest the tree "
            "too deeply, or subtype_id doesn't fit the article_type."
        },
        404: {"description": "No article exists with the given ID."},
    },
)
async def update_article(
    article_id: int,
    data: Annotated[
        ArticleUpdate,
        Body(
            openapi_examples={
                "rewrite": {
                    "summary": "Edit title and body",
                    "value": {"title": "Khazad-dum, the Dwarrowdelf", "body_markdown": "Updated lore text..."},
                },
                "reparent": {
                    "summary": "Move under a different parent",
                    "value": {"parent_id": 12},
                },
            }
        ),
    ],
    article_service: ArticleCrudDep,
    gm_user: GmUserDep,
):
    """
    Partially update an article's fields. **Author or founder only** (403 for another GM).

    Only fields included in the request body are changed; use
    `PUT /articles/{article_id}/tags` for tags. Including `parent_id`
    re-roots `path` for this article and its whole existing subtree. `status` can't be
    changed here — use the `submit`/`publish`/`reject`/`archive`/`restore` actions. The author may edit their
    article in any status, a published one included (it stays published); the founder may edit any article;
    same title/`:::gm` rules as on create.

    Every change of the content fields (title, excerpt, body, type, subtype, visibility) is saved as a new
    version (`version` in the response; history under `/articles/{article_id}/revisions`). The optional
    `change_note` is stored with that version.
    """

    return await article_service.update_article(article_id, data, ArticleActor.of(gm_user))


@router.delete(
    "/{article_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an article",
    responses={
        404: {"description": "No article exists with the given ID."},
    },
)
async def delete_article(article_id: int, article_service: ArticleCrudDep, _: FounderDep):
    """
    Delete an article. **Founder only.**

    Child articles (`parent_id` pointing at this one) are detached, not
    deleted (`ondelete="SET NULL"`); its tag links and relations are
    removed (cascade).
    """

    await article_service.delete(article_id)
    return None
