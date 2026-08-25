"""Tests for the GM max-level system: cap writes, level-up gating, and the can-level-up check."""

import pytest
import pytest_asyncio

from app.models import CharacterMaxLevel


@pytest_asyncio.fixture
async def create_capped_character(create_api_character):
    """Create a character via the API keeping its raw creation state (level-up cap seeded at 1)."""

    async def _create(class_id, owner=None, **kwargs):
        return await create_api_character(class_id, owner=owner, raise_max_level=False, **kwargs)

    return _create


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelMaxLevel:
    async def test_gm_can_raise_max_level(self, client, gm, gm_token, create_class, create_capped_character):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=gm)

        response = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            json={"max_level": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "character_id": character["id"],
            "current_level": 1,
            "max_level": 3,
        }

    async def test_creation_seeds_cap_at_starting_level(
        self, client, player, player_token, create_class, create_capped_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=player)

        response = await client.get(
            "/characters/progression/can-level-up",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json() == {"can_level_up": False, "current_level": 1, "max_level": 1}

    async def test_lowering_max_level_returns_400(self, client, gm, gm_token, create_class, create_capped_character):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=gm)
        headers = {"Authorization": f"Bearer {gm_token}"}
        url = "/characters/gm-panel/max-level"
        params = {"character_id": character["id"]}

        raise_response = await client.patch(url, params=params, json={"max_level": 5}, headers=headers)
        assert raise_response.status_code == 200

        lower_response = await client.patch(url, params=params, json={"max_level": 3}, headers=headers)
        assert lower_response.status_code == 400
        assert "only be raised" in lower_response.json()["error"]["message"]

        same_response = await client.patch(url, params=params, json={"max_level": 5}, headers=headers)
        assert same_response.status_code == 400

    async def test_max_level_below_current_level_returns_400(
        self, client, gm, gm_token, db_session, create_class, create_character
    ):
        """Defensive check: a stored cap below the character's level can never happen via the API."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, level=3)

        row = await db_session.get(CharacterMaxLevel, character.id)
        row.max_level = 1
        await db_session.commit()

        response = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character.id},
            json={"max_level": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert "already level 3" in response.json()["error"]["message"]

    async def test_player_denied_max_level_write(
        self, client, player, player_token, create_class, create_capped_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=player)

        response = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            json={"max_level": 5},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_owner_can_read_max_level_but_not_write(
        self, client, player, player_token, create_class, create_capped_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=player)

        read_response = await client.get(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert read_response.status_code == 200
        assert read_response.json()["max_level"] == 1

        write_response = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            json={"max_level": 5},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert write_response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestLevelUpCap:
    async def test_level_up_blocked_at_cap(self, client, player, player_token, create_class, create_capped_character):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=player)

        response = await client.post(
            "/characters/progression/level-up",
            params={"character_id": character["id"]},
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400
        assert "maximum allowed level" in response.json()["error"]["message"]

    async def test_raise_cap_then_level_up(
        self, client, player, player_token, gm_token, create_class, create_capped_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_capped_character(character_class.id, owner=player)
        headers = {"Authorization": f"Bearer {player_token}"}
        gm_headers = {"Authorization": f"Bearer {gm_token}"}

        raise_response = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            json={"max_level": 2},
            headers=gm_headers,
        )
        assert raise_response.status_code == 200

        can_response = await client.get(
            "/characters/progression/can-level-up", params={"character_id": character["id"]}, headers=headers
        )
        assert can_response.json() == {"can_level_up": True, "current_level": 1, "max_level": 2}

        level_up_response = await client.post(
            "/characters/progression/level-up", params={"character_id": character["id"]}, json={}, headers=headers
        )
        assert level_up_response.status_code == 200
        assert level_up_response.json()["level"] == 2

        exhausted_response = await client.get(
            "/characters/progression/can-level-up", params={"character_id": character["id"]}, headers=headers
        )
        assert exhausted_response.json() == {"can_level_up": False, "current_level": 2, "max_level": 2}
