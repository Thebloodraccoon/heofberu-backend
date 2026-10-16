"""Unit tests for the character access helpers (app/features/characters/access.py)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.constants import UserRole
from app.features.characters.access import (
    can_manage_character,
    check_character_access,
    ensure_character_access,
    get_character_for_gm,
    get_character_for_user,
    is_gm,
)
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse


def make_user(user_id, role=UserRole.PLAYER):
    return UserResponse(id=user_id, username="u", email="u@example.com", role=role, created_at=datetime(2026, 1, 1))


class FakeRepository:
    """Character 1 is owned by ``owner_id`` and active in a campaign run by each id in ``managed_by``."""

    def __init__(self, owner_id=7, managed_by=()):
        self.owner_id = owner_id
        self.managed_by = set(managed_by)
        self.calls = []

    async def get_owner_id(self, character_id):
        self.calls.append(("owner", character_id))
        return self.owner_id if character_id == 1 else None

    async def get_by_id(self, character_id):
        self.calls.append(("full", character_id))
        return SimpleNamespace(id=1, owner_id=self.owner_id) if character_id == 1 else None

    async def get_by_id_light(self, character_id):
        self.calls.append(("light", character_id))
        return SimpleNamespace(id=1, owner_id=self.owner_id) if character_id == 1 else None

    async def is_managed_by(self, character_id, gm_id):
        self.calls.append(("managed", character_id, gm_id))
        return gm_id in self.managed_by


@pytest.mark.unit
class TestIsGm:
    @pytest.mark.parametrize(
        ("role", "expected"),
        [(UserRole.GM, True), (UserRole.FOUND_FATHER, True), (UserRole.PLAYER, False)],
    )
    def test_gm_and_founder_are_gms(self, role, expected):
        assert is_gm(make_user(1, role)) is expected


@pytest.mark.unit
@pytest.mark.asyncio
class TestCanManageCharacter:
    async def test_founder_manages_everything_without_a_lookup(self):
        repository = FakeRepository()

        assert await can_manage_character(repository, 1, make_user(99, UserRole.FOUND_FATHER)) is True
        assert repository.calls == []

    async def test_gm_of_the_characters_campaign_manages_it(self):
        assert await can_manage_character(FakeRepository(managed_by={99}), 1, make_user(99, UserRole.GM)) is True

    async def test_other_gm_does_not(self):
        assert await can_manage_character(FakeRepository(managed_by={50}), 1, make_user(99, UserRole.GM)) is False

    async def test_player_never_manages_and_is_not_looked_up(self):
        repository = FakeRepository(managed_by={99})

        assert await can_manage_character(repository, 1, make_user(99)) is False
        assert repository.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckCharacterAccess:
    async def test_owner_is_allowed_without_a_campaign_lookup(self):
        repository = FakeRepository()

        await check_character_access(repository, SimpleNamespace(id=1, owner_id=7), make_user(7))

        assert repository.calls == []

    async def test_other_player_is_denied(self):
        with pytest.raises(CharacterAccessDeniedException):
            await check_character_access(FakeRepository(), SimpleNamespace(id=1, owner_id=7), make_user(8))

    async def test_gm_role_alone_is_not_enough(self):
        with pytest.raises(CharacterAccessDeniedException):
            await check_character_access(
                FakeRepository(), SimpleNamespace(id=1, owner_id=7), make_user(99, UserRole.GM)
            )

    async def test_campaign_gm_is_allowed(self):
        await check_character_access(
            FakeRepository(managed_by={99}), SimpleNamespace(id=1, owner_id=7), make_user(99, UserRole.GM)
        )

    async def test_founder_is_allowed(self):
        await check_character_access(
            FakeRepository(), SimpleNamespace(id=1, owner_id=7), make_user(99, UserRole.FOUND_FATHER)
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestEnsureCharacterAccess:
    async def test_only_the_owner_id_is_looked_up_for_the_owner(self):
        repository = FakeRepository()

        await ensure_character_access(repository, 1, make_user(7))

        assert repository.calls == [("owner", 1)]

    async def test_unknown_character_is_404(self):
        with pytest.raises(CharacterNotFoundException):
            await ensure_character_access(FakeRepository(), 2, make_user(7))

    async def test_other_player_is_denied(self):
        with pytest.raises(CharacterAccessDeniedException):
            await ensure_character_access(FakeRepository(), 1, make_user(8))

    async def test_founder_is_allowed(self):
        await ensure_character_access(FakeRepository(), 1, make_user(99, UserRole.FOUND_FATHER))

    async def test_campaign_gm_is_allowed(self):
        repository = FakeRepository(managed_by={99})

        await ensure_character_access(repository, 1, make_user(99, UserRole.GM))

        assert repository.calls == [("owner", 1), ("managed", 1, 99)]

    async def test_other_gm_is_denied(self):
        with pytest.raises(CharacterAccessDeniedException):
            await ensure_character_access(FakeRepository(managed_by={50}), 1, make_user(99, UserRole.GM))


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCharacterForUser:
    async def test_light_flag_selects_the_light_fetch(self):
        repository = FakeRepository()

        await get_character_for_user(repository, 1, make_user(7), light=True)
        await get_character_for_user(repository, 1, make_user(7))

        assert repository.calls == [("light", 1), ("full", 1)]

    async def test_unknown_character_is_404_before_the_access_check(self):
        with pytest.raises(CharacterNotFoundException):
            await get_character_for_user(FakeRepository(), 2, make_user(8))


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCharacterForGm:
    """GM-panel writes: the campaign GM or the founder; owning the sheet grants nothing."""

    async def test_campaign_gm_gets_the_character(self):
        repository = FakeRepository(managed_by={99})

        character = await get_character_for_gm(repository, 1, make_user(99, UserRole.GM))

        assert character.id == 1

    async def test_founder_gets_it_without_a_campaign_lookup(self):
        repository = FakeRepository()

        await get_character_for_gm(repository, 1, make_user(99, UserRole.FOUND_FATHER))

        assert repository.calls == [("full", 1)]

    async def test_owner_gm_playing_in_another_gms_campaign_is_denied(self):
        repository = FakeRepository(owner_id=7, managed_by={50})

        with pytest.raises(CharacterAccessDeniedException):
            await get_character_for_gm(repository, 1, make_user(7, UserRole.GM))

    async def test_owner_gm_of_their_own_campaign_is_allowed(self):
        await get_character_for_gm(FakeRepository(owner_id=7, managed_by={7}), 1, make_user(7, UserRole.GM))

    async def test_other_gm_is_denied(self):
        with pytest.raises(CharacterAccessDeniedException):
            await get_character_for_gm(FakeRepository(managed_by={50}), 1, make_user(99, UserRole.GM))

    async def test_unknown_character_is_404_before_the_access_check(self):
        repository = FakeRepository()

        with pytest.raises(CharacterNotFoundException):
            await get_character_for_gm(repository, 2, make_user(99, UserRole.GM))

        assert repository.calls == [("full", 2)]
