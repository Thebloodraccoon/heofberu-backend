"""
Behavior that follows from grant effects being computed on read rather than
stored: GM proficiency checks see feature-granted proficiencies, the GM can
only remove spells they granted themselves, and a GM feature edit reaches
existing characters through the set-based grant sync.
"""

import pytest


async def _grant_feature_with_effects(client, gm_token, character_id: int, feature_id: int, effects: dict) -> None:
    fx_resp = await client.put(
        f"/features/{feature_id}/effects", json=effects, headers={"Authorization": f"Bearer {gm_token}"}
    )
    assert fx_resp.status_code == 200, fx_resp.text

    grant_resp = await client.post(
        f"/characters/{character_id}/gm-panel/features",
        json={"feature_id": feature_id},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert grant_resp.status_code == 201, grant_resp.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmProficiencyChecksSeeFeatureGrants:
    async def test_gm_can_revoke_a_skill_granted_only_by_a_feature(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Sneaky", source_type="CLASS", level=None)
        await _grant_feature_with_effects(
            client,
            gm_token,
            character.id,
            feature.id,
            {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
        )

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            params={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204, remove_resp.text

        read_resp = await client.get(
            f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert skill.id not in [s["skill_id"] for s in read_resp.json()["skills"]]

    async def test_gm_adding_a_skill_a_feature_already_grants_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Acrobatics", ability="DEX")
        feature = await create_feature(name="Nimble", source_type="CLASS", level=None)
        await _grant_feature_with_effects(
            client,
            gm_token,
            character.id,
            feature.id,
            {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
        )

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            json={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 409

    async def test_gm_can_revoke_a_saving_throw_granted_only_by_a_feature(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Fighter")).id)
        feature = await create_feature(name="Resilient", source_type="CLASS", level=None)
        await _grant_feature_with_effects(
            client,
            gm_token,
            character.id,
            feature.id,
            {"static_groups": [{"effect_type": "saving_throw", "items": [{"ability": "CON"}]}]},
        )

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            params={"ability": "CON"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204, remove_resp.text

        read_resp = await client.get(
            f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert "CON" not in [s["ability"] for s in read_resp.json()["saving_throws"]]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmCanOnlyRemoveOwnSpells:
    async def test_gm_and_feature_spells_are_separate_lists_and_only_gm_ones_are_removable(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Wizard")).id)
        feature_spell = await create_spell(name="Mage Hand", school="CONJURATION", level="CANTRIP")
        gm_spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")
        feature = await create_feature(name="Arcane Gift", source_type="CLASS", level=None)
        await _grant_feature_with_effects(
            client,
            gm_token,
            character.id,
            feature.id,
            {"static_groups": [{"effect_type": "spell", "items": [{"spell_id": feature_spell.id}]}]},
        )

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/spells",
            json={"spell_id": gm_spell.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text

        body = (
            await client.get(f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()
        assert [s["id"] for s in body["gm_spells"]] == [gm_spell.id]
        assert [s["id"] for s in body["feature_spells"]] == [feature_spell.id]

        for spell_id, expected in ((feature_spell.id, 404), (gm_spell.id, 204)):
            remove_resp = await client.delete(
                f"/characters/{character.id}/gm-panel/spells",
                params={"spell_id": spell_id},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert remove_resp.status_code == expected

        body = (
            await client.get(f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()
        assert body["gm_spells"] == []
        assert [s["id"] for s in body["feature_spells"]] == [feature_spell.id]


@pytest.mark.integration
@pytest.mark.asyncio
class TestSourceFeatureSyncReachesExistingCharacters:
    async def test_new_class_feature_is_granted_and_raised_level_revokes_it(
        self, client, gm_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Barbarian")
        character, token = await create_api_character(class_id=character_class.id)

        created = await client.post(
            "/features",
            json={"name": "Danger Sense", "source_type": "CLASS", "class_id": character_class.id, "level": 1},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201, created.text
        feature_id = created.json()["id"]

        def feature_ids(response) -> list[int]:
            return [grant["feature_id"] for grant in response.json()]

        granted = await client.get(
            f"/characters/{character['id']}/features", headers={"Authorization": f"Bearer {token}"}
        )
        assert feature_id in feature_ids(granted)

        raised = await client.patch(
            f"/features/{feature_id}", json={"level": 5}, headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert raised.status_code == 200, raised.text

        revoked = await client.get(
            f"/characters/{character['id']}/features", headers={"Authorization": f"Bearer {token}"}
        )
        assert feature_id not in feature_ids(revoked)
