"""Tests for the character backstory endpoints (uncached get / upsert)."""

import pytest
from sqlalchemy import select

from app.constants import BACKSTORY_MAX_LENGTH
from app.models import CharacterBackstory


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterBackstory:
    async def test_new_character_has_an_empty_backstory(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.get(f"/characters/{character.id}/backstory", headers=auth(player_token))

        assert response.status_code == 200
        assert response.json() == {"character_id": character.id, "content": ""}

    async def test_put_creates_then_replaces_the_backstory(
        self, client, db_session, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        url = f"/characters/{character.id}/backstory"

        first = await client.put(url, json={"content": "Born in a forge."}, headers=auth(player_token))
        second = await client.put(url, json={"content": "Rewritten."}, headers=auth(player_token))
        read = await client.get(url, headers=auth(player_token))

        assert first.status_code == 200
        assert second.json()["content"] == "Rewritten."
        assert read.json()["content"] == "Rewritten."
        rows = (
            await db_session.scalars(select(CharacterBackstory).where(CharacterBackstory.character_id == character.id))
        ).all()
        assert len(rows) == 1

    async def test_empty_string_clears_the_backstory(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        url = f"/characters/{character.id}/backstory"
        await client.put(url, json={"content": "Something"}, headers=auth(player_token))

        response = await client.put(url, json={"content": ""}, headers=auth(player_token))

        assert response.status_code == 200
        assert response.json()["content"] == ""

    async def test_empty_body_no_longer_wipes_the_backstory(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        url = f"/characters/{character.id}/backstory"
        await client.put(url, json={"content": "Keep me"}, headers=auth(player_token))

        response = await client.put(url, json={}, headers=auth(player_token))

        assert response.status_code == 422
        assert (await client.get(url, headers=auth(player_token))).json()["content"] == "Keep me"

    async def test_content_over_the_limit_is_rejected_and_the_limit_is_accepted(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        url = f"/characters/{character.id}/backstory"

        too_long = await client.put(url, json={"content": "x" * (BACKSTORY_MAX_LENGTH + 1)}, headers=auth(player_token))
        at_limit = await client.put(url, json={"content": "x" * BACKSTORY_MAX_LENGTH}, headers=auth(player_token))

        assert too_long.status_code == 422
        assert at_limit.status_code == 200

    async def test_other_player_cannot_read_or_write(
        self, client, player_token, create_user, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=fighter.id)
        url = f"/characters/{character.id}/backstory"

        assert (await client.get(url, headers=auth(player_token))).status_code == 403
        assert (await client.put(url, json={"content": "x"}, headers=auth(player_token))).status_code == 403

    async def test_gm_can_edit_any_backstory(self, client, gm_token, player, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.put(
            f"/characters/{character.id}/backstory", json={"content": "GM edit"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["content"] == "GM edit"

    async def test_unknown_character_is_404(self, client, player_token):
        assert (await client.get("/characters/999999/backstory", headers=auth(player_token))).status_code == 404
        response = await client.put("/characters/999999/backstory", json={"content": "x"}, headers=auth(player_token))
        assert response.status_code == 404

    async def test_creation_from_a_background_stores_its_description_as_the_backstory(
        self, client, player_token, create_class, create_background
    ):
        fighter = await create_class(name="Fighter")
        background = await create_background()
        created = await client.post(
            "/characters",
            json={
                "name": "Hero",
                "class_id": fighter.id,
                "background_id": background.id,
                "suggestion_ids": [s.id for s in background.suggestions],
            },
            headers=auth(player_token),
        )

        response = await client.get(f"/characters/{created.json()['id']}/backstory", headers=auth(player_token))

        assert response.status_code == 200
        assert response.json()["content"] == (background.description or "")
