"""The owner's public-visibility switch and the anonymous public character card."""

import pytest

from app.constants import UserRole


def auth(token):
    return {"Authorization": f"Bearer {token}"}


BACKSTORY = "Raised by smugglers.\n:::gm\nSecretly sold out his crew.\n:::\nNow seeks redemption."


@pytest.mark.integration
@pytest.mark.asyncio
class TestPublicVisibility:
    async def test_hidden_by_default(self, client, free_character):
        response = await client.get(f"/characters/{free_character.id}/public")

        assert response.status_code == 404

    @pytest.mark.parametrize("role", [UserRole.GM, UserRole.FOUND_FATHER])
    async def test_nobody_but_the_owner_reveals_a_character(self, client, create_user, login_as, free_character, role):
        token = await login_as(await create_user(role=role))

        response = await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "full"},
            headers=auth(token),
        )

        assert response.status_code == 403

    async def test_concept_level_no_longer_exists(self, client, player_token, free_character):
        response = await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "concept"},
            headers=auth(player_token),
        )

        assert response.status_code == 422

    async def test_full_card_strips_gm_secrets_from_the_backstory(self, client, player_token, free_character):
        await client.put(
            f"/characters/{free_character.id}/backstory", json={"content": BACKSTORY}, headers=auth(player_token)
        )
        await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "full"},
            headers=auth(player_token),
        )

        card = (await client.get(f"/characters/{free_character.id}/public")).json()

        assert "Raised by smugglers." in card["backstory"]
        assert "sold out his crew" not in card["backstory"]
        assert card["name"] == "Gurn"
        assert "class_name" not in card
        assert card["class_id"] == free_character.class_id
        assert card["level"] == free_character.level
        assert card["base_ability_scores"]["strength"] == free_character.strength
        assert isinstance(card["skill_proficiencies"], list)
        assert isinstance(card["saving_throw_proficiencies"], list)
        assert "items" not in card
        assert "spells" not in card

    async def test_full_card_strips_gm_secrets_from_personality(self, client, player_token, free_character):
        fields = ("personality_traits", "ideals", "bonds", "flaws")
        personality = {field: f"Public {field}.\n:::gm\nSecret {field}.\n:::" for field in fields}
        updated = await client.patch(f"/characters/{free_character.id}", json=personality, headers=auth(player_token))
        assert updated.status_code == 200, updated.text
        await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "full"},
            headers=auth(player_token),
        )

        card = (await client.get(f"/characters/{free_character.id}/public")).json()
        sheet = (await client.get(f"/characters/{free_character.id}", headers=auth(player_token))).json()

        for field in fields:
            assert f"Public {field}." in card[field]
            assert f"Secret {field}." not in card[field]
            assert f"Secret {field}." in sheet[field]

    async def test_sheet_reports_the_visibility(self, client, player_token, free_character):
        await client.patch(
            f"/characters/{free_character.id}/public-visibility",
            json={"public_visibility": "full"},
            headers=auth(player_token),
        )

        sheet = await client.get(f"/characters/{free_character.id}", headers=auth(player_token))

        assert sheet.json()["public_visibility"] == "full"
