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
            "/feats/ability-score-increases",
            params={"feat_id": feat.id},
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"]: item["amount"] for item in response.json()["ability_score_increases"]} == {"STR": 1}

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

    async def test_delete_feat_granted_to_character_returns_409(
        self, client, founder_token, gm_token, player, create_class, create_character, create_feat
    ):
        feat = await create_feat(name="Popular Feat")
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        # Feat grants are a GM-panel write.
        add_response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        response = await client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/feats/{feat.id}")).status_code == 200

    async def test_feats_have_no_feature_endpoints(self, client, gm_token, create_feat):
        """Feats own no features (a feat is de facto its own feature) — the nested endpoints are gone."""

        feat = await create_feat(name="Alert")

        assert (
            await client.get(
                f"/feats/{feat.id}/features",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404

    async def test_creating_feat_source_feature_is_rejected(self, client, gm_token, create_feat):
        """The FEAT feature source type no longer exists."""

        feat = await create_feat(name="Alert")

        response = await client.post(
            "/features",
            json={"name": "Alert Initiative", "source_type": "FEAT", "feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422
