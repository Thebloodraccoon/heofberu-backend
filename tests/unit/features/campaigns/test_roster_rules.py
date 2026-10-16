"""Unit tests for the roster status rule and the services' clock hook (no database)."""

from datetime import datetime, timezone

import pytest

from app.constants import CampaignCharacterStatus as Status
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.characters.service import status_change_allowed


@pytest.mark.unit
class TestStatusChangeAllowed:
    @pytest.mark.parametrize("target", [Status.DEAD, Status.RETIRED, Status.REMOVED])
    def test_an_active_participation_can_end_any_way(self, target):
        assert status_change_allowed(Status.ACTIVE, target)

    @pytest.mark.parametrize("current", [Status.DEAD, Status.RETIRED])
    def test_an_ended_participation_can_still_be_removed(self, current):
        assert status_change_allowed(current, Status.REMOVED)

    @pytest.mark.parametrize(
        ("current", "target"),
        [(Status.DEAD, Status.RETIRED), (Status.RETIRED, Status.DEAD), (Status.REMOVED, Status.DEAD)],
    )
    def test_ended_participations_dont_move_sideways(self, current, target):
        assert not status_change_allowed(current, target)

    @pytest.mark.parametrize("current", [Status.DEAD, Status.RETIRED, Status.REMOVED])
    def test_nothing_goes_back_to_active(self, current):
        assert not status_change_allowed(current, Status.ACTIVE)

    @pytest.mark.parametrize("status", list(Status))
    def test_the_same_status_is_a_no_op(self, status):
        assert status_change_allowed(status, status)


@pytest.mark.unit
class TestClock:
    def test_default_is_aware_utc(self):
        assert CampaignScopedService(repository=None).clock().tzinfo is timezone.utc

    def test_an_instance_can_pin_it(self):
        fixed = datetime(2099, 1, 1, tzinfo=timezone.utc)
        service = CampaignScopedService(repository=None)

        service.clock = lambda: fixed

        assert service.clock() == fixed
        assert CampaignScopedService(repository=None).clock() != fixed
