"""Tests for GM feat endpoints: grant, update, revoke."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterFeats:
    async def test_grant_and_list_feat(self, client, gm, gm_token, create_class, create_character, create_feat):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feat = await create_feat(name="Alert")

        grant_response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert grant_response.status_code == 201
        assert grant_response.json()["feat_id"] == feat.id

        list_response = await client.get(
            "/characters/feats",
            params={"character_id": character.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert list_response.status_code == 200
        assert [item["feat_id"] for item in list_response.json()] == [feat.id]

    async def test_duplicate_feat_grant_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_feat
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feat = await create_feat(name="Alert")

        await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 409

    async def test_grant_feat_whose_prerequisite_is_unmet_returns_400(
        self, client, gm, gm_token, create_class, create_character, create_feat
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feat = await create_feat(
            name="Heavy Armor Master",
            prerequisite_ability="STR",
            prerequisite_minimum_score=13,
        )

        response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_grant_feat_with_asi_choice(self, client, gm, gm_token, create_class, create_character, create_feat):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=13)
        feat = await create_feat(name="Resilient")
        asi_response = await client.put(
            "/feats/ability-score-increases",
            params={"feat_id": feat.id},
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        grant_response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id, "ability_score_increase_id": asi_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert grant_response.status_code == 201
        assert grant_response.json()["ability_score_increase_id"] == asi_id

    async def test_revoke_feat(self, client, gm, gm_token, create_class, create_character, create_feat):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        feat = await create_feat(name="Alert")

        grant_response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_feat_id = grant_response.json()["id"]

        response = await client.delete(
            "/characters/gm-panel/feats",
            params={"character_id": character.id, "feat_id": character_feat_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                "/characters/feats",
                params={"character_id": character.id},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json() == []

    async def test_player_denied_feat_grant(
        self, client, player, player_token, create_class, create_character, create_feat
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        feat = await create_feat(name="Alert")

        response = await client.post(
            "/characters/gm-panel/feats",
            params={"character_id": character.id},
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
