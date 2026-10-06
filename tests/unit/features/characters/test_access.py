"""Unit tests for the character access helpers (app/features/characters/access.py)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.constants import UserRole
from app.features.characters.access import (
    check_character_access,
    ensure_character_access,
    get_character_for_user,
    is_gm,
)
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse


def make_user(user_id, role=UserRole.PLAYER):
    return UserResponse(id=user_id, username="u", email="u@example.com", role=role, created_at=datetime(2026, 1, 1))


class FakeRepository:
    def __init__(self, owner_id=7):
        self.owner_id = owner_id
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


@pytest.mark.unit
class TestIsGm:
    @pytest.mark.parametrize(
        ("role", "expected"),
        [(UserRole.GM, True), (UserRole.FOUND_FATHER, True), (UserRole.PLAYER, False)],
    )
    def test_gm_and_founder_are_gms(self, role, expected):
        assert is_gm(make_user(1, role)) is expected


@pytest.mark.unit
class TestCheckCharacterAccess:
    def test_owner_is_allowed(self):
        check_character_access(SimpleNamespace(owner_id=7), make_user(7))

    def test_other_player_is_denied(self):
        with pytest.raises(CharacterAccessDeniedException):
            check_character_access(SimpleNamespace(owner_id=7), make_user(8))

    @pytest.mark.parametrize("role", [UserRole.GM, UserRole.FOUND_FATHER])
    def test_gm_roles_bypass_ownership(self, role):
        check_character_access(SimpleNamespace(owner_id=7), make_user(99, role))


@pytest.mark.unit
@pytest.mark.asyncio
class TestEnsureCharacterAccess:
    async def test_only_the_owner_id_is_looked_up(self):
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
