"""Proposed article changes (mounted under ``/articles/{article_id}``)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.constants import ArticleProposalStatus
from app.core.pagination import CursorPage, CursorQuery, Page, PaginationQuery, use_cursor
from app.features.articles.access import ArticleActor
from app.features.articles.crud.schemas import ArticleContentUpdate, ArticleResponse
from app.features.articles.dependencies import ArticleProposalsDep
from app.features.articles.proposals.schemas import (
    ArticleProposalBrief,
    ArticleProposalReject,
    ArticleProposalReplace,
    ArticleProposalResponse,
)
from app.features.articles.revisions.schemas import ArticleRevisionDiff
from app.features.auth.dependencies import GmUserDep

router = APIRouter()
#: Mounted under ``/articles``: the cross-article review queue.
queue_router = APIRouter()

StatusesQuery = Annotated[
    list[ArticleProposalStatus] | None,
    Query(
        alias="status",
        description="Only proposals in these states (repeat the key: `?status=accepted&status=rejected`).",
    ),
]

PROPOSAL_404: dict[int | str, dict[str, Any]] = {404: {"description": "No such article, or it has no such proposal."}}
CONFLICT_409 = (
    "The proposal conflicts with the current version: `details` holds `conflicts` (`field`, `base`, `current`, "
    "`proposed`), `body_conflicts` (`base`, `current`, `proposed` hunks) and `merged_body` (with "
    "`<<<<<<<`/`|||||||`/`=======`/`>>>>>>>` markers). Nothing is saved."
)
CHANGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **PROPOSAL_404,
    403: {"description": "Only the proposer, the article's author or the founder can update a proposal."},
}
REVIEW_RESPONSES: dict[int | str, dict[str, Any]] = {
    **PROPOSAL_404,
    403: {"description": "Only the article's author or the founder reviews proposals (the founder, their own too)."},
}


@router.post(
    "/proposals",
    response_model=ArticleProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a change to an article",
    responses={
        404: {"description": "No article exists with the given ID."},
        409: {"description": "The caller is the article's author: edit it directly instead."},
    },
)
async def propose_article_change(
    article_id: int, data: ArticleContentUpdate, proposals: ArticleProposalsDep, gm_user: GmUserDep
):
    """
    Propose new content for an article written by another GM (any status). Fields left out keep the current
    version's values; the proposal is based on that version (`base_version`). **GM only**, not the author: the
    founder may propose too, to leave a change to the author's judgement.
    """

    return await proposals.propose(article_id, data, ArticleActor.of(gm_user))


@queue_router.get(
    "/proposals",
    response_model=Page[ArticleProposalBrief] | CursorPage[ArticleProposalBrief],
    summary="Proposals across all articles (review queue)",
    responses={422: {"description": "Invalid `cursor`."}},
)
async def list_all_proposals(
    proposals: ArticleProposalsDep,
    gm_user: GmUserDep,
    statuses: StatusesQuery = None,
    mine: bool = Query(False, description="Only proposals to articles you wrote (what awaits your decision)."),
    proposer_id: int | None = Query(None, description="Only proposals made by this GM (`your id` = your proposals)."),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    pagination: PaginationQuery = "page",
    cursor: CursorQuery = None,
):
    """
    Return proposals across all articles, newest first, each with its `article` (`id`, `title`, `slug`):
    `?status=pending&mine=true` is your review queue. Offset `Page` by default, keyset `CursorPage` with
    `pagination=cursor`. **GM only.**
    """

    return await proposals.queue(
        ArticleActor.of(gm_user),
        statuses,
        mine=mine,
        proposer_id=proposer_id,
        page=page,
        size=size,
        cursor=cursor,
        use_cursor=use_cursor(pagination, cursor),
    )


@router.get(
    "/proposals",
    response_model=Page[ArticleProposalBrief] | CursorPage[ArticleProposalBrief],
    summary="List an article's proposals",
    responses={404: {"description": "No article exists with the given ID."}, 422: {"description": "Invalid `cursor`."}},
)
async def list_article_proposals(
    article_id: int,
    proposals: ArticleProposalsDep,
    _: GmUserDep,
    statuses: StatusesQuery = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    pagination: PaginationQuery = "page",
    cursor: CursorQuery = None,
):
    """
    Return the article's proposals, newest first. Offset `Page` by default, keyset `CursorPage` with
    `pagination=cursor`. **GM only.**
    """

    return await proposals.list_proposals(
        article_id,
        statuses,
        page=page,
        size=size,
        cursor=cursor,
        use_cursor=use_cursor(pagination, cursor),
    )


@router.get(
    "/proposals/{proposal_id}",
    response_model=ArticleProposalResponse,
    summary="Get one proposal",
    responses=PROPOSAL_404,
)
async def get_article_proposal(article_id: int, proposal_id: int, proposals: ArticleProposalsDep, _: GmUserDep):
    """Return the full proposed content, `:::gm` blocks included. **GM only.**"""

    return await proposals.get_proposal(article_id, proposal_id)


@router.get(
    "/proposals/{proposal_id}/diff",
    response_model=ArticleRevisionDiff,
    summary="Compare a proposal with the version it is based on",
    responses=PROPOSAL_404,
)
async def diff_article_proposal(article_id: int, proposal_id: int, proposals: ArticleProposalsDep, _: GmUserDep):
    """
    Show what the proposal changes relative to its `base_version` (`against`); `version` is the version it would
    become. Same shape as the revision diff. **GM only.**
    """

    return await proposals.diff(article_id, proposal_id)


@router.post(
    "/proposals/{proposal_id}/accept",
    response_model=ArticleResponse,
    summary="Accept a proposal",
    responses={
        **REVIEW_RESPONSES,
        409: {
            "description": "Already closed; the article was edited after the proposal's base version (without "
            "`rebase`); or, with `rebase`, a merge conflict (see the rebase endpoint)."
        },
    },
)
async def accept_article_proposal(
    article_id: int,
    proposal_id: int,
    proposals: ArticleProposalsDep,
    gm_user: GmUserDep,
    rebase: bool = Query(False, description="Merge a stale proposal onto the current version first."),
):
    """
    Apply the proposal as the article's next version: the history records the proposer as `editor_id` and you as
    `reviewer_id`. With `rebase=true` a stale proposal is merged onto the current version first (409 with the
    conflicts if it can't be). **Author or founder only.**
    """

    return await proposals.accept(article_id, proposal_id, ArticleActor.of(gm_user), rebase=rebase)


@router.post(
    "/proposals/{proposal_id}/rebase",
    response_model=ArticleProposalResponse,
    summary="Rebase a stale proposal onto the current version",
    responses={**CHANGE_RESPONSES, 409: {"description": f"Already closed. Or: {CONFLICT_409}"}},
)
async def rebase_article_proposal(
    article_id: int, proposal_id: int, proposals: ArticleProposalsDep, gm_user: GmUserDep
):
    """
    Three-way merge of the proposal onto the article's current version, like `git rebase`: what only one side
    changed is kept, the body is merged line by line. Without conflicts the proposal is rewritten with
    `base_version` = the current version (then it can be accepted); a current proposal is returned unchanged.
    **The proposer, the article's author or the founder.**
    """

    return await proposals.rebase(article_id, proposal_id, ArticleActor.of(gm_user))


@router.put(
    "/proposals/{proposal_id}",
    response_model=ArticleProposalResponse,
    summary="Replace a proposal's content",
    responses={
        **CHANGE_RESPONSES,
        400: {"description": "The subtype doesn't exist or belongs to another article_type."},
        409: {"description": "Already closed, or `base_version` isn't the article's current version."},
    },
)
async def replace_article_proposal(
    article_id: int,
    proposal_id: int,
    data: ArticleProposalReplace,
    proposals: ArticleProposalsDep,
    gm_user: GmUserDep,
):
    """
    Replace the whole content of a pending proposal, e.g. after resolving rebase conflicts by hand.
    `base_version` must be the article's current version. **The proposer, the article's author or the founder.**
    """

    return await proposals.replace(article_id, proposal_id, data, ArticleActor.of(gm_user))


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ArticleProposalResponse,
    summary="Reject a proposal",
    responses={**REVIEW_RESPONSES, 409: {"description": "Already accepted/rejected/withdrawn."}},
)
async def reject_article_proposal(
    article_id: int,
    proposal_id: int,
    proposals: ArticleProposalsDep,
    gm_user: GmUserDep,
    data: ArticleProposalReject | None = None,
):
    """
    Close the proposal without applying it; you are recorded as `reviewer_id` and the optional `reason` as
    `review_note`. **Author or founder only.**
    """

    return await proposals.reject(article_id, proposal_id, ArticleActor.of(gm_user), data.reason if data else None)


@router.post(
    "/proposals/{proposal_id}/withdraw",
    response_model=ArticleProposalResponse,
    summary="Withdraw your proposal",
    responses={
        **PROPOSAL_404,
        403: {"description": "Only the GM who made the proposal can withdraw it."},
        409: {"description": "Already accepted/rejected/withdrawn."},
    },
)
async def withdraw_article_proposal(
    article_id: int, proposal_id: int, proposals: ArticleProposalsDep, gm_user: GmUserDep
):
    """Take back your own pending proposal (status `withdrawn`). **The proposer only.**"""

    return await proposals.withdraw(article_id, proposal_id, ArticleActor.of(gm_user))
