"""Tests for the feat write endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatCrud:
    async def test_player_cannot_create_feat(self, client, player_token):
        response = await client.post(
            "/feats",
            json={"name": "Custom Feat"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_feat(self, client, gm_token):
        response = await client.post(
            "/feats",
            json={"name": "Alert"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Alert"

    async def test_create_duplicate_feat_name_returns_400(self, client, gm_token, create_feat):
        await create_feat(name="Lucky")
        response = await client.post(
            "/feats",
            json={"name": "Lucky"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_update_feat(self, client, gm_token, create_feat):
        feat = await create_feat(name="Old Name")

        response = await client.patch(
            f"/feats/{feat.id}", json={"name": "New Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    async def test_gm_can_set_ability_score_increases(self, client, gm_token, create_feat):
        feat = await create_feat(name="Resilient")

        response = await client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"]: item["amount"] for item in response.json()["ability_score_increases"]} == {"STR": 1}

    async def test_gm_can_create_feat_with_nested_features(self, client, gm_token):
        response = await client.post(
            "/feats",
            json={
                "name": "Alert",
                "features": [
                    {"name": "Alert Initiative", "description": "You gain a +5 bonus to initiative."},
                    {"name": "Cannot Be Surprised", "description": "You can't be surprised while conscious."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert [item["name"] for item in response.json()["features"]] == ["Alert Initiative", "Cannot Be Surprised"]

        feat_id = response.json()["id"]
        fetched = await client.get(f"/feats/{feat_id}")
        assert fetched.status_code == 200
        assert [item["name"] for item in fetched.json()["features"]] == ["Alert Initiative", "Cannot Be Surprised"]

    async def test_gm_cannot_delete_feat(self, client, gm_token, create_feat):
        feat = await create_feat(name="Doomed Feat")

        response = await client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/feats/{feat.id}")).status_code == 200

    async def test_founder_can_delete_feat(self, client, founder_token, create_feat):
        feat = await create_feat(name="Doomed Feat")

        response = await client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/feats/{feat.id}")).status_code == 404

    async def test_founder_can_delete_feat_with_features_cascades_them(self, client, founder_token, create_feat):
        await create_feat(name="Doomed Feat")

        response = await client.post(
            "/feats",
            json={"name": "With Benefit", "features": [{"name": "Benefit", "description": "Something useful."}]},
            headers={"Authorization": f"Bearer {founder_token}"},
        )
        assert response.status_code == 201
        feat_id = response.json()["id"]
        feature_id = response.json()["features"][0]["id"]

        delete_response = await client.delete(f"/feats/{feat_id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert delete_response.status_code == 204
        assert (await client.get(f"/feats/{feat_id}")).status_code == 404
        assert (await client.get(f"/features/{feature_id}")).status_code == 404

    async def test_delete_feat_granted_to_character_returns_409(
        self, client, founder_token, player_token, player, create_class, create_character, create_feat
    ):
        feat = await create_feat(name="Popular Feat")
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        add_response = await client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = await client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/feats/{feat.id}")).status_code == 200

    async def test_player_cannot_add_feat_feature(self, client, player_token, create_feat):
        feat = await create_feat(name="Alert")

        response = await client.post(
            f"/feats/{feat.id}/features",
            json={"name": "Alert Initiative"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_feat_features(self, client, gm_token, create_feat):
        feat = await create_feat(name="Alert")

        added = await client.post(
            f"/feats/{feat.id}/features",
            json={"name": "Alert Initiative", "description": "You gain a +5 bonus to initiative."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()["features"][0]
        assert feature["name"] == "Alert Initiative"

        updated = await client.patch(
            f"/feats/{feat.id}/features/{feature['id']}",
            json={"description": "You gain a +10 bonus to initiative."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        updated_feature = updated.json()["features"][0]
        assert updated_feature["id"] == feature["id"]
        assert updated_feature["description"] == "You gain a +10 bonus to initiative."

        removed = await client.delete(
            f"/feats/{feat.id}/features/{feature['id']}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        fetched = await client.get(f"/feats/{feat.id}")
        assert fetched.json()["features"] == []

    async def test_update_feat_feature_of_another_source_returns_400(self, client, gm_token, create_feat, create_feature):
        feat = await create_feat(name="Alert")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.patch(
            f"/feats/{feat.id}/features/{foreign.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_remove_feat_feature_of_another_source_returns_400(self, client, gm_token, create_feat, create_feature):
        feat = await create_feat(name="Alert")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.delete(
            f"/feats/{feat.id}/features/{foreign.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_feat_feature_endpoints_return_404(self, client, gm_token):
        assert (
            await client.post(
                "/feats/9999/features",
                json={"name": "Alert Initiative"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.patch(
                "/feats/9999/features/1",
                json={"name": "Renamed"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.delete(
                "/feats/9999/features/1",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404

    async def test_delete_feat_whose_feature_is_granted_to_character_returns_409(
        self,
        client,
        founder_token,
        player_token,
        player,
        create_class,
        create_character,
        create_feat,
        create_feature,
    ):
        feat = await create_feat(name="Popular Feat")
        benefit = await create_feature(name="Benefit", source_type="FEAT", feat_id=feat.id)
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        add_response = await client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": benefit.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = await client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/feats/{feat.id}")).status_code == 200
