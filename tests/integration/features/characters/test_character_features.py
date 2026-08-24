"""Tests for GM feature endpoints: record, update, remove."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterFeatures:
    async def test_add_and_list_feature(self, client, gm, gm_token, create_class, create_character, create_feature):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Extra Attack", source_type="OTHER")

        add_response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id, "notes": "Two attacks"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["feature_id"] == feature.id
        assert add_response.json()["notes"] == "Two attacks"

        list_response = await client.get(
            "/characters/features",
            params={"character_id": character.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert list_response.status_code == 200
        assert [item["feature_id"] for item in list_response.json()] == [feature.id]

    async def test_response_embeds_brief_feature_details(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1)

        add_response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id, "notes": "Once per short rest"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert add_response.status_code == 201
        embedded = add_response.json()["feature"]
        assert embedded["id"] == feature.id
        assert embedded["name"] == "Second Wind"
        assert embedded["source_type"] == "CLASS"
        assert "description" in embedded

    async def test_add_missing_feature_returns_404(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_duplicate_feature_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Extra Attack", source_type="OTHER")

        await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 409

    async def test_update_feature_notes(self, client, gm, gm_token, create_class, create_character, create_feature):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Fighting Style", source_type="OTHER")
        add_response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id, "notes": "Defense"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_feature_id = add_response.json()["id"]

        response = await client.patch(
            "/characters/gm-panel/features",
            params={"character_id": character.id, "feature_id": character_feature_id},
            json={"notes": "Dueling"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["notes"] == "Dueling"

    async def test_remove_feature(self, client, gm, gm_token, create_class, create_character, create_feature):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Extra Attack", source_type="OTHER")
        add_response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_feature_id = add_response.json()["id"]

        response = await client.delete(
            "/characters/gm-panel/features",
            params={"character_id": character.id, "feature_id": character_feature_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                "/characters/features",
                params={"character_id": character.id},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json() == []

    async def test_player_denied_feature_grant(
        self, client, player, player_token, create_class, create_character, create_feature
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        feature = await create_feature(name="Extra Attack", source_type="OTHER")

        response = await client.post(
            "/characters/gm-panel/features",
            params={"character_id": character.id},
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
