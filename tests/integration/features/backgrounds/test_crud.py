"""Tests for the background write endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundCrud:
    async def test_player_cannot_create_background(self, client, player_token):
        response = await client.post(
            "/backgrounds",
            json={"name": "Custom"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_background(self, client, gm_token):
        response = await client.post(
            "/backgrounds",
            json={"name": "Hermit"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Hermit"

    async def test_create_duplicate_background_name_returns_400(self, client, gm_token, create_background):
        await create_background(name="Acolyte")
        response = await client.post(
            "/backgrounds",
            json={"name": "Acolyte"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_set_granted_skills(self, client, gm_token, create_background, create_skill):
        background = await create_background(name="Sage")
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = await client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["granted_skills"]] == [skill.id]

    async def test_gm_can_create_background_then_add_features(self, client, gm_token):
        """BackgroundCreate stays minimal: nested features are attached through the features endpoint."""

        response = await client.post(
            "/backgrounds",
            json={"name": "Acolyte"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        background_id = response.json()["id"]

        assert (await client.get(f"/backgrounds/{background_id}/features")).json() == []

        added = await client.post(
            f"/backgrounds/{background_id}/features",
            json={"name": "Shelter of the Faithful", "description": "Free healing and care at a temple."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201

        fetched = await client.get(f"/backgrounds/{background_id}/features")
        assert fetched.status_code == 200
        assert [item["name"] for item in fetched.json()] == ["Shelter of the Faithful"]

    async def test_gm_can_set_background_starting_items(self, client, gm_token, create_background, create_item):
        background = await create_background(name="Acolyte")
        censer = await create_item(name="Censer", item_type="ADVENTURING_GEAR")

        response = await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": [{"item_id": censer.id, "quantity": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [(entry["item_id"], entry["quantity"]) for entry in response.json()["starting_items"]] == [
            (censer.id, 1)
        ]

        fetched = await client.get(f"/backgrounds/{background.id}/items")
        assert fetched.status_code == 200
        assert [entry["item"]["name"] for entry in fetched.json()] == ["Censer"]

    async def test_set_background_starting_items_invalid_item_returns_400(self, client, gm_token, create_background):
        background = await create_background(name="Acolyte")

        response = await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": [{"item_id": 9999, "quantity": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_player_cannot_set_background_starting_items(self, client, player_token, create_background):
        background = await create_background(name="Acolyte")

        response = await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_cannot_delete_background(self, client, gm_token, create_background):
        background = await create_background(name="Doomed Background")

        response = await client.delete(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/backgrounds/{background.id}")).status_code == 200

    async def test_founder_can_delete_background(self, client, founder_token, create_background):
        background = await create_background(name="Doomed Background")

        response = await client.delete(
            f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 204
        assert (await client.get(f"/backgrounds/{background.id}")).status_code == 404

    async def test_delete_background_whose_feature_is_granted_to_character_returns_409(
        self,
        client,
        founder_token,
        player_token,
        player,
        create_class,
        create_character,
        create_background,
        create_feature,
    ):
        background = await create_background(name="Popular Background")
        shelter = await create_feature(
            name="Shelter of the Faithful", source_type="BACKGROUND", background_id=background.id
        )
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        add_response = await client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": shelter.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = await client.delete(
            f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 409
        assert (await client.get(f"/backgrounds/{background.id}")).status_code == 200

    async def test_player_cannot_add_background_feature(self, client, player_token, create_background):
        background = await create_background(name="Acolyte")

        response = await client.post(
            f"/backgrounds/{background.id}/features",
            json={"name": "Shelter of the Faithful"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_background_features(self, client, gm_token, create_background):
        background = await create_background(name="Acolyte")

        added = await client.post(
            f"/backgrounds/{background.id}/features",
            json={"name": "Shelter of the Faithful", "description": "Free healing at a temple."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()
        assert feature["name"] == "Shelter of the Faithful"

        updated = await client.patch(
            f"/backgrounds/{background.id}/features/{feature['id']}",
            json={"description": "Free healing and care at a shrine."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        updated_feature = updated.json()
        assert updated_feature["id"] == feature["id"]
        assert updated_feature["description"] == "Free healing and care at a shrine."

        removed = await client.delete(
            f"/backgrounds/{background.id}/features/{feature['id']}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        fetched = await client.get(f"/backgrounds/{background.id}/features")
        assert fetched.json() == []

    async def test_update_background_feature_of_another_source_returns_400(
        self, client, gm_token, create_background, create_feature
    ):
        background = await create_background(name="Acolyte")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.patch(
            f"/backgrounds/{background.id}/features/{foreign.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_remove_background_feature_of_another_source_returns_400(
        self, client, gm_token, create_background, create_feature
    ):
        background = await create_background(name="Acolyte")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.delete(
            f"/backgrounds/{background.id}/features/{foreign.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_background_feature_endpoints_return_404(self, client, gm_token):
        assert (
            await client.post(
                "/backgrounds/9999/features",
                json={"name": "Shelter of the Faithful"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.patch(
                "/backgrounds/9999/features/1",
                json={"name": "Renamed"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.delete(
                "/backgrounds/9999/features/1",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
