"""Shared fixtures for character feature tests."""

import pytest


@pytest.fixture
def create_caster_class(client, gm_token, create_class):
    """Create a class with a spell-slot progression at level 1, via the API."""

    def _create_caster_class(name="Wizard", slots=None):
        character_class = create_class(name=name, hit_dice="D6", spellcasting_ability="INT")
        slots = slots or [{"spell_level": "LEVEL_1", "slots": 2}]
        response = client.put(
            f"/classes/{character_class.id}/spell-slots/1",
            json={"slots": slots},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200, response.text
        return character_class

    return _create_caster_class


@pytest.fixture
def create_api_character(client, login_as, create_user):
    """Create a character via the API and return the created payload + owner token."""

    def _create_api_character(
        class_id,
        owner=None,
        name="Test Character",
        level=1,
        race_id=None,
        background_id=None,
        **kwargs,
    ):
        if owner is None:
            owner = create_user()
        token = login_as(owner)
        response = client.post(
            "/characters/",
            json={
                "name": name,
                "level": level,
                "class_id": class_id,
                "race_id": race_id,
                "background_id": background_id,
                **kwargs,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201, response.text
        return response.json(), token

    return _create_api_character
