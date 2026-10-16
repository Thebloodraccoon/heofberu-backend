"""
Review endpoints: campaign and session reviews (``router``) and the founder's moderation of campaign reviews
(``moderation_router``) and of session reviews (``session_moderation_router``).
"""

from fastapi import APIRouter, Query, status

from app.core.pagination import Page
from app.features.auth.dependencies import CurrentUserDep, FounderDep
from app.features.campaigns.dependencies import CampaignReviewsDep
from app.features.campaigns.reviews.schemas import (
    CampaignReviewResponse,
    CampaignReviewWrite,
    SessionReviewResponse,
    SessionReviewWrite,
)

router = APIRouter()
moderation_router = APIRouter()
session_moderation_router = APIRouter()

_NOT_FOUND = {404: {"description": "No such campaign/session/review, or you may not see it."}}
_PLAYER_ONLY = {**_NOT_FOUND, 403: {"description": "Only players of the campaign write reviews."}}
_SESSION = "/{campaign_id:int}/sessions/{session_id:int}"


@router.get(
    "/{campaign_id:int}/reviews",
    response_model=Page[CampaignReviewResponse],
    summary="List a campaign's reviews",
    responses=_NOT_FOUND,
)
async def list_campaign_reviews(
    campaign_id: int,
    service: CampaignReviewsDep,
    current_user: CurrentUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """The players' reviews of the campaign, oldest first (also shown on its public campaign)."""

    return await service.list_campaign_reviews(campaign_id, current_user, page=page, size=size)


@router.put(
    "/{campaign_id:int}/review",
    response_model=CampaignReviewResponse,
    summary="Write my review of a campaign",
    responses=_PLAYER_ONLY,
)
async def put_campaign_review(
    campaign_id: int, data: CampaignReviewWrite, service: CampaignReviewsDep, current_user: CurrentUserDep
):
    """
    Create or replace your review of the whole campaign. It is public: it also appears on the public campaign this
    campaign was made from. **Players of the campaign only.**
    """

    return await service.put_campaign_review(campaign_id, data, current_user)


@router.delete(
    "/{campaign_id:int}/review",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my review of a campaign",
    responses=_NOT_FOUND,
)
async def delete_campaign_review(campaign_id: int, service: CampaignReviewsDep, current_user: CurrentUserDep):
    """Delete your own review of the campaign."""

    await service.delete_campaign_review(campaign_id, current_user)


@router.get(
    _SESSION + "/reviews",
    response_model=Page[SessionReviewResponse],
    summary="List a session's reviews",
    responses=_NOT_FOUND,
)
async def list_session_reviews(
    campaign_id: int,
    session_id: int,
    service: CampaignReviewsDep,
    current_user: CurrentUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """The GM sees every review; a player sees their own and those opened to the table."""

    return await service.list_session_reviews(campaign_id, session_id, current_user, page=page, size=size)


@router.put(
    _SESSION + "/review",
    response_model=SessionReviewResponse,
    summary="Write my review of a session",
    responses=_PLAYER_ONLY,
)
async def put_session_review(
    campaign_id: int,
    session_id: int,
    data: SessionReviewWrite,
    service: CampaignReviewsDep,
    current_user: CurrentUserDep,
):
    """
    Create or replace your review of a published session. The GM always reads it; with `visible_to_table` the
    other players do too. **Players of the campaign only.**
    """

    return await service.put_session_review(campaign_id, session_id, data, current_user)


@router.delete(
    _SESSION + "/review",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my review of a session",
    responses=_NOT_FOUND,
)
async def delete_session_review(
    campaign_id: int, session_id: int, service: CampaignReviewsDep, current_user: CurrentUserDep
):
    """Delete your own review of the session."""

    await service.delete_session_review(campaign_id, session_id, current_user)


@moderation_router.post(
    "/{review_id:int}/hide",
    response_model=CampaignReviewResponse,
    summary="Hide a campaign review",
    responses={404: {"description": "No such review."}},
)
async def hide_campaign_review(review_id: int, service: CampaignReviewsDep, _: FounderDep):
    """Hide a review everywhere (campaign and public campaign). **Founder only.**"""

    return await service.set_campaign_review_hidden(review_id, True)


@moderation_router.post(
    "/{review_id:int}/unhide",
    response_model=CampaignReviewResponse,
    summary="Unhide a campaign review",
    responses={404: {"description": "No such review."}},
)
async def unhide_campaign_review(review_id: int, service: CampaignReviewsDep, _: FounderDep):
    """Show a hidden review again. **Founder only.**"""

    return await service.set_campaign_review_hidden(review_id, False)


@session_moderation_router.post(
    "/{review_id:int}/hide",
    response_model=SessionReviewResponse,
    summary="Hide a session review",
    responses={404: {"description": "No such review."}},
)
async def hide_session_review(review_id: int, service: CampaignReviewsDep, _: FounderDep):
    """Hide a session review from the GM and the table. **Founder only.**"""

    return await service.set_session_review_hidden(review_id, True)


@session_moderation_router.post(
    "/{review_id:int}/unhide",
    response_model=SessionReviewResponse,
    summary="Unhide a session review",
    responses={404: {"description": "No such review."}},
)
async def unhide_session_review(review_id: int, service: CampaignReviewsDep, _: FounderDep):
    """Show a hidden session review again. **Founder only.**"""

    return await service.set_session_review_hidden(review_id, False)
