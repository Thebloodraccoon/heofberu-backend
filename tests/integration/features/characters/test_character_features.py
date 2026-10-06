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
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["feature_id"] == feature.id

        list_response = await client.get(
            f"/characters/{character.id}/features",
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
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
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
            f"/characters/{character.id}/gm-panel/features",
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
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 409

    async def test_remove_feature(self, client, gm, gm_token, create_class, create_character, create_feature):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feature = await create_feature(name="Extra Attack", source_type="OTHER")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_feature_id = add_response.json()["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/features",
            params={"feature_id": character_feature_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                f"/characters/{character.id}/features",
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
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_feats_do_not_leak_into_features(
        self, client, gm, gm_token, create_class, create_api_character, create_feature, create_feat
    ):
        """A GM-granted feat is surfaced via /feats, never duplicated under /features (which excludes FEAT)."""
        character_class = await create_class(name="Fighter")
        second_wind = await create_feature(
            name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=gm)

        feat = await create_feat(name="Alert")
        grant = await client.post(
            f"/characters/{character['id']}/gm-panel/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant.status_code == 201

        features_response = await client.get(
            f"/characters/{character['id']}/features",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert features_response.status_code == 200
        feature_ids = [item["feature_id"] for item in features_response.json()]
        assert feature_ids == [second_wind.id]

        feats_response = await client.get(
            f"/characters/{character['id']}/feats",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert feats_response.status_code == 200
        assert [item["feat_id"] for item in feats_response.json()] == [feat.id]
