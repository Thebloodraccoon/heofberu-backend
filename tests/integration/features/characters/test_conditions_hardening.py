"""Boundary, null-PATCH and race tests for the character condition endpoints."""

import asyncio
from datetime import datetime

import pytest

from app.constants import ConditionType, UserRole
from app.features.characters.conditions.exceptions import CharacterConditionAlreadyExistsException
from app.features.characters.conditions.schemas import CharacterConditionAdd
from app.features.characters.conditions.service import CharacterConditionService
from app.features.users.schemas import UserResponse
from app.settings import settings


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterConditionsHardening:
    async def test_patch_with_null_source_is_a_422(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        await client.post(
            f"/characters/{character.id}/conditions",
            json={"condition": "POISONED", "source": "spider"},
            headers=auth(player_token),
        )

        response = await client.patch(
            f"/characters/{character.id}/conditions/POISONED",
            json={"source": None},
            headers=auth(player_token),
        )

        assert response.status_code == 422

    async def test_oversized_source_is_a_422(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.post(
            f"/characters/{character.id}/conditions",
            json={"condition": "POISONED", "source": "x" * 1_001},
            headers=auth(player_token),
        )

        assert response.status_code == 422

    async def test_concurrent_duplicate_adds_end_in_one_success_and_conflicts(
        self, db_session, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        character_id = character.id
        user = UserResponse(
            id=player.id, username="p", email="p@example.com", role=UserRole.PLAYER, created_at=datetime(2026, 1, 1)
        )

        async def add():
            session = settings.SessionLocal()
            try:
                return await CharacterConditionService(session).add_condition(
                    character_id, CharacterConditionAdd(condition=ConditionType.PRONE), user
                )
            finally:
                await session.close()

        results = await asyncio.gather(*(add() for _ in range(4)), return_exceptions=True)

        conflicts = [r for r in results if isinstance(r, CharacterConditionAlreadyExistsException)]
        assert len(conflicts) == 3
        assert len([r for r in results if not isinstance(r, Exception)]) == 1

    async def test_unknown_character_is_404(self, client, player_token):
        response = await client.get("/characters/999999/conditions", headers=auth(player_token))

        assert response.status_code == 404

    async def test_gm_can_manage_conditions_of_any_character(
        self, client, gm_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.post(
            f"/characters/{character.id}/conditions", json={"condition": "PRONE"}, headers=auth(gm_token)
        )

        assert response.status_code == 201
