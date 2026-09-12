"""
GM-panel proficiency endpoints: add/remove a character's free-form skill,
saving-throw, armor, and weapon proficiency rows (``GmPanelProficiencyService``).
The skill-expertise toggle is already covered in ``test_gm_panel.py``.
"""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelSkillProficiency:
    async def test_gm_can_add_and_remove_skill_proficiency(
        self, client, gm, gm_token, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            json={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["skill_id"] == skill.id

        read_resp = await client.get(
            f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert skill.id in [s["skill_id"] for s in read_resp.json()["skills"]]

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            params={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

        read_resp2 = await client.get(
            f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert skill.id not in [s["skill_id"] for s in read_resp2.json()["skills"]]

    async def test_adding_already_granted_skill_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")

        first = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            json={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            json={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 409

    async def test_removing_ungranted_skill_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_skill
    ):
        character_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        skill = await create_skill(key="RELIGION", name="Religion", ability="INT")

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/skills",
            params={"skill_id": skill.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelSavingThrowProficiency:
    async def test_gm_can_add_and_remove_saving_throw(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            json={"ability": "INT"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["ability"] == "INT"

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            params={"ability": "INT"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

    async def test_adding_already_granted_saving_throw_returns_409(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        first = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            json={"ability": "WIS"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            json={"ability": "WIS"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 409

    async def test_removing_ungranted_saving_throw_returns_404(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/saving-throws",
            params={"ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelArmorProficiency:
    async def test_gm_can_add_and_remove_armor(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/armor",
            json={"armor_type": "HEAVY"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["armor_type"] == "HEAVY"

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/armor",
            params={"armor_type": "HEAVY"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

    async def test_adding_already_granted_armor_returns_409(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        first = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/armor",
            json={"armor_type": "MEDIUM"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/armor",
            json={"armor_type": "MEDIUM"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 409

    async def test_removing_ungranted_armor_returns_404(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/armor",
            params={"armor_type": "SHIELD"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmPanelWeaponProficiency:
    async def test_gm_can_add_and_remove_weapon_category(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            json={"weapon_category": "MARTIAL"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["weapon_category"] == "MARTIAL"

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            params={"weapon_category": "MARTIAL"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

    async def test_gm_can_add_and_remove_weapon_item(
        self, client, gm, gm_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        longsword = await create_item(name="Longsword")

        add_resp = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            json={"item_id": longsword.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["item_id"] == longsword.id

        remove_resp = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            params={"item_id": longsword.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_resp.status_code == 204

    async def test_adding_both_category_and_item_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)
        dagger = await create_item(name="Dagger")

        response = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            json={"weapon_category": "SIMPLE", "item_id": dagger.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 422

    async def test_adding_already_granted_weapon_category_returns_409(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        first = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            json={"weapon_category": "SIMPLE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            json={"weapon_category": "SIMPLE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert second.status_code == 409

    async def test_removing_ungranted_weapon_returns_404(self, client, gm, gm_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            params={"weapon_category": "MARTIAL"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404

    async def test_removing_without_category_or_item_returns_422(
        self, client, gm, gm_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/proficiencies/weapons",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 422
