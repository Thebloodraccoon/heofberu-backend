"""GM-panel endpoints: grant/revoke a free-form (non-feature) spell on a character."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelGrantedSpells:
    async def test_gm_can_grant_and_revoke_a_spell(
        self, client, gm, gm_token, create_class, create_character, create_spell
    ):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["spell_id"] == spell.id
        granted_spell_id = add_resp.json()["id"]

        read_resp = await client.get(
            f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert spell.id in [s["spell_id"] for s in read_resp.json()["granted_spells"]]

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/spells",
            params={"granted_spell_id": granted_spell_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

        read_resp2 = await client.get(
            f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert spell.id not in [s["spell_id"] for s in read_resp2.json()["granted_spells"]]

    async def test_granting_nonexistent_spell_returns_404(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/spells",
            json={"spell_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404

    async def test_removing_nonexistent_granted_spell_returns_404(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/spells",
            params={"granted_spell_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404

    async def test_removing_a_feature_granted_spell_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        """A spell that came from a feature/feat grant can't be revoked directly — revoke the grant instead."""

        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        cantrip = await create_spell(name="Prestidigitation", school="TRANSMUTATION", level="CANTRIP")
        feature = await create_feature(name="Bonus Cantrip", source_type="CLASS", level=None)

        fx_resp = await client.put(
            f"/features/{feature.id}/effects",
            json={"spell_effects": [{"spell_id": cantrip.id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert fx_resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text

        spells_resp = await client.get(
            f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"}
        )
        granted = spells_resp.json()["granted_spells"]
        assert len(granted) == 1
        granted_spell_id = granted[0]["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/spells",
            params={"granted_spell_id": granted_spell_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 409

    async def test_player_cannot_grant_spell(self, client, player_token, create_class, create_character, gm, create_spell):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        response = await client.post(
            f"/characters/{character.id}/gm-panel/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 403
