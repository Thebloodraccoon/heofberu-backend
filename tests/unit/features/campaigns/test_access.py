"""Unit tests for the campaign permission resolver (app/features/campaigns/access.py)."""

from types import SimpleNamespace

import pytest

from app.constants import UserRole
from app.features.campaigns.access import CampaignContext
from app.features.campaigns.exceptions import (
    CampaignGmOnlyException,
    CampaignNotFoundException,
    CampaignOwnReviewException,
    CampaignPlayerOnlyException,
)

OWNER_ID = 10


def context(user_id, role=UserRole.PLAYER, *, is_player=False):
    return CampaignContext.of(SimpleNamespace(id=user_id, role=role), 1, OWNER_ID, is_player)


@pytest.mark.unit
class TestCampaignContext:
    def test_owner_is_gm(self):
        ctx = context(OWNER_ID, UserRole.GM)

        assert (ctx.is_gm, ctx.can_read, ctx.role) == (True, True, "gm")
        assert ctx.ensure_gm() is ctx

    def test_founder_is_gm_of_every_campaign(self):
        ctx = context(1, UserRole.FOUND_FATHER)

        assert ctx.is_gm and ctx.can_read
        ctx.ensure_gm()

    def test_player_reads_but_is_not_gm(self):
        ctx = context(20, is_player=True)

        assert (ctx.is_gm, ctx.can_read, ctx.role) == (False, True, "player")
        ctx.ensure_can_read()
        with pytest.raises(CampaignGmOnlyException):
            ctx.ensure_gm()

    @pytest.mark.parametrize("role", [UserRole.PLAYER, UserRole.GM])
    def test_outsider_gets_404_even_with_the_gm_role(self, role):
        ctx = context(30, role)

        assert ctx.can_read is False
        with pytest.raises(CampaignNotFoundException):
            ctx.ensure_can_read()
        with pytest.raises(CampaignNotFoundException):
            ctx.ensure_gm()

    def test_only_players_write_reviews(self):
        context(20, is_player=True).ensure_player()
        with pytest.raises(CampaignPlayerOnlyException):
            context(OWNER_ID, UserRole.GM).ensure_player()

    def test_gm_who_also_plays_is_both(self):
        ctx = context(OWNER_ID, UserRole.GM, is_player=True)

        assert ctx.is_gm and ctx.is_player
        ctx.ensure_player()

    def test_gm_who_also_plays_still_does_not_review_their_campaign(self):
        context(20, is_player=True).ensure_reviewer()
        with pytest.raises(CampaignOwnReviewException):
            context(OWNER_ID, UserRole.GM, is_player=True).ensure_reviewer()
        with pytest.raises(CampaignPlayerOnlyException):
            context(OWNER_ID, UserRole.GM).ensure_reviewer()

    def test_campaign_of_a_deleted_gm_is_run_by_the_founder_only(self):
        def orphan(user_id, role):
            return CampaignContext.of(SimpleNamespace(id=user_id, role=role), 1, None, False)

        assert orphan(1, UserRole.FOUND_FATHER).is_gm
        assert not orphan(OWNER_ID, UserRole.GM).can_read
