"""Shared fixtures for character feature tests."""

import pytest_asyncio

from app.constants import CHARACTER_MAX_LEVEL


@pytest_asyncio.fixture
async def create_caster_class(client, gm_token, create_class):
    """Create a class with a spell-slot progression at level 1, via the API."""

    async def _create_caster_class(name="Wizard", slots=None):
        character_class = await create_class(name=name, hit_dice="D6", spellcasting_ability="INT")
        slots = slots or [{"spell_level": "LEVEL_1", "slots": 2}]
        response = await client.put(
            f"/classes/{character_class.id}/spell-slots/1",
            json={"slots": slots},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200, response.text
        return character_class

    return _create_caster_class


@pytest_asyncio.fixture
async def create_api_character(client, login_as, create_user, create_background, gm_token):
    """
    Create a character via the API and return the created payload + owner token.

    Characters are created with their GM-set level-up cap seeded at 1; by
    default this fixture raises it to ``CHARACTER_MAX_LEVEL`` (20) via the
    GM panel so tests that level up freely keep working. Pass
    ``raise_max_level=False`` to keep the raw level-1 cap (used by the
    max-level system's own tests).
    """

    async def _create_api_character(
        class_id,
        owner=None,
        name="Test Character",
        race_id=None,
        background_id=None,
        raise_max_level=True,
        **kwargs,
    ):
        if owner is None:
            owner = await create_user()
        if background_id is None:
            background_id = (await create_background()).id
        token = await login_as(owner)
        response = await client.post(
            "/characters",
            json={
                "name": name,
                "class_id": class_id,
                "race_id": race_id,
                "background_id": background_id,
                **kwargs,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201, response.text
        character = response.json()

        if raise_max_level and character["level"] < CHARACTER_MAX_LEVEL:
            raise_response = await client.patch(
                f"/characters/{character['id']}/gm-panel/max-level",
                json={"max_level": CHARACTER_MAX_LEVEL},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert raise_response.status_code == 200, raise_response.text

        return character, token

    return _create_api_character
