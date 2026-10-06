"""Article review-workflow endpoints: submit, publish, reject, archive, restore."""

from typing import Any

from fastapi import APIRouter, Query

from app.features.articles.access import ArticleActor
from app.features.articles.crud.schemas import ArticleResponse
from app.features.articles.dependencies import ArticleWorkflowDep
from app.features.auth.dependencies import FounderDep, GmUserDep

router = APIRouter()

TRANSITION_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "`submit` by a GM who isn't the author."},
    404: {"description": "No article exists with the given ID."},
    409: {
        "description": "The action isn't allowed from the article's current status, "
        "or (`publish`) the article was edited after the `version` you reviewed."
    },
}


@router.post(
    "/{article_id:int}/submit",
    response_model=ArticleResponse,
    summary="Send a draft for review",
    responses=TRANSITION_RESPONSES,
)
async def submit_article(article_id: int, workflow: ArticleWorkflowDep, gm_user: GmUserDep):
    """`draft` → `in_review`. **Author or founder only** (403 for another GM)."""

    return await workflow.transition(article_id, "submit", actor=ArticleActor.of(gm_user))


@router.post(
    "/{article_id:int}/publish",
    response_model=ArticleResponse,
    summary="Approve and publish an article under review",
    responses=TRANSITION_RESPONSES,
)
async def publish_article(
    article_id: int,
    workflow: ArticleWorkflowDep,
    founder: FounderDep,
    version: int = Query(
        ...,
        ge=1,
        description="The `version` of the article you reviewed. Publishing fails with 409 if it was edited since.",
    ),
):
    """
    `in_review` → `published`; records the reviewer, the first publish stamps `published_at`. **Founder only.**

    Pass the `version` you reviewed (`GET /articles/{id}`, changes via `GET /articles/{id}/revisions/{version}/diff`):
    if the author edited the article after that, the response is 409 and nothing is published.
    """

    return await workflow.transition(article_id, "publish", actor=ArticleActor.of(founder), expected_version=version)


@router.post(
    "/{article_id:int}/reject",
    response_model=ArticleResponse,
    summary="Send an article under review back to draft",
    responses=TRANSITION_RESPONSES,
)
async def reject_article(article_id: int, workflow: ArticleWorkflowDep, founder: FounderDep):
    """`in_review` → `draft`; records the reviewer. **Founder only.**"""

    return await workflow.transition(article_id, "reject", actor=ArticleActor.of(founder))


@router.post(
    "/{article_id:int}/archive",
    response_model=ArticleResponse,
    summary="Archive an article",
    responses=TRANSITION_RESPONSES,
)
async def archive_article(article_id: int, workflow: ArticleWorkflowDep, founder: FounderDep):
    """`draft` / `in_review` / `published` → `archived` (hidden from non-GMs). **Founder only.**"""

    return await workflow.transition(article_id, "archive", actor=ArticleActor.of(founder))


@router.post(
    "/{article_id:int}/restore",
    response_model=ArticleResponse,
    summary="Restore an archived article to draft",
    responses=TRANSITION_RESPONSES,
)
async def restore_article(article_id: int, workflow: ArticleWorkflowDep, founder: FounderDep):
    """`archived` → `draft`. **Founder only.**"""

    return await workflow.transition(article_id, "restore", actor=ArticleActor.of(founder))
