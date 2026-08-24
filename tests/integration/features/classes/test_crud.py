"""Tests for the class write endpoints."""

import pytest
from sqlalchemy import func, select


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassCrud:
    async def test_player_cannot_create_class(self, client, player_token):
        response = await client.post(
            "/classes",
            json={"name": "Homebrew", "hit_dice": "D8", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_non_caster_class(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Fighter"
        assert body["spellcasting_ability"] is None

    async def test_gm_can_create_caster_class(self, client, gm_token, create_skill):
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = await client.post(
            "/classes",
            json={
                "name": "Wizard",
                "hit_dice": "D6",
                "spellcasting_ability": "INT",
                "primary_abilities": ["INT"],
                "saving_throws": ["INT", "WIS"],
                "available_skills": [skill.id],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["spellcasting_ability"] == "INT"
        assert body["primary_abilities"] == [{"ability": "INT"}]
        assert body["saving_throws"] == [{"ability": "INT"}, {"ability": "WIS"}]
        assert [item["id"] for item in body["available_skills"]] == [skill.id]

    async def test_create_class_ignores_nested_fields(self, client, gm_token):
        """ClassCreate stays minimal: nested features/subclasses/spell slots are not part of create."""

        response = await client.post(
            "/classes",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "features": [
                    {"name": "Second Wind", "description": "Once per short rest."},
                    {"name": "Extra Attack", "description": "Attack twice.", "level": 5},
                ],
                "subclasses": [{"name": "Champion", "unlock_level": 3}],
                "spell_slot_progression": [
                    {
                        "class_level": 1,
                        "slots": [{"spell_level": "CANTRIP", "slots": 3}, {"spell_level": "LEVEL_1", "slots": 2}],
                    }
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        class_id = response.json()["id"]

        fetched = await client.get("/classes/features", params={"class_id": class_id})
        assert fetched.status_code == 200
        assert fetched.json() == []

        body = (await client.get(f"/classes/{class_id}")).json()
        assert body["spell_slot_progression"] == []
        assert body["subclasses"] == []

    async def test_gm_can_set_spell_slot_progression(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        level_one = await client.put(
            "/classes/spell-slots",
            params={"class_id": character_class.id, "class_level": 1},
            json={"slots": [{"spell_level": "CANTRIP", "slots": 3}, {"spell_level": "LEVEL_1", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert level_one.status_code == 200

        level_five = await client.put(
            "/classes/spell-slots",
            params={"class_id": character_class.id, "class_level": 5},
            json={"slots": [{"spell_level": "LEVEL_3", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert level_five.status_code == 200

        fetched = (await client.get(f"/classes/{character_class.id}")).json()
        assert fetched["spell_slot_progression"] == [
            {"class_level": 1, "spell_level": "CANTRIP", "slots": 3},
            {"class_level": 1, "spell_level": "LEVEL_1", "slots": 2},
            {"class_level": 5, "spell_level": "LEVEL_3", "slots": 2},
        ]

    async def test_gm_can_create_subclass_then_add_features(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        created = await client.post(
            "/classes/subclasses",
            params={"class_id": character_class.id},
            json={"name": "Champion"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        subclass_id = created.json()["id"]

        added = await client.post(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass_id},
            json={"name": "Improved Critical", "level": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201

        fetched = await client.get(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass_id},
        )
        assert fetched.status_code == 200
        assert [item["name"] for item in fetched.json()] == ["Improved Critical"]

    async def test_create_class_spellcasting_ability_not_primary_returns_400(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={"name": "Bad Caster", "hit_dice": "D8", "spellcasting_ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_duplicate_class_name_returns_400(self, client, gm_token, create_class):
        await create_class(name="Fighter")
        response = await client.post(
            "/classes",
            json={"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_update_class(self, client, gm_token, create_class):
        character_class = await create_class(name="Old Name")

        response = await client.patch(
            f"/classes/{character_class.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    async def test_update_primary_abilities_dropping_spellcasting_ability_returns_400(
        self, client, gm_token, create_class
    ):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.patch(
            f"/classes/{character_class.id}",
            json={"primary_abilities": ["WIS"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_replace_saving_throws(self, client, gm_token, create_class):
        character_class = await create_class(name="Dexy")

        response = await client.put(
            "/classes/saving-throws",
            params={"class_id": character_class.id},
            json={"saving_throws": ["DEX", "INT"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"] for item in response.json()["saving_throws"]} == {"DEX", "INT"}

    async def test_gm_can_set_available_skills(self, client, gm_token, create_class, create_skill):
        character_class = await create_class(name="Skillful")
        skill = await create_skill(key="PERSUASION", name="Persuasion", ability="CHA")

        response = await client.put(
            "/classes/available-skills",
            params={"class_id": character_class.id},
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["available_skills"]] == [skill.id]

    async def test_gm_can_set_spell_slots(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            "/classes/spell-slots",
            params={"class_id": character_class.id, "class_level": 1},
            json={"slots": [{"spell_level": "LEVEL_1", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200

    async def test_set_spell_slots_invalid_level_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            "/classes/spell-slots",
            params={"class_id": character_class.id, "class_level": 21},
            json={"slots": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_create_class_with_armor_proficiencies(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "armor_proficiencies": ["LIGHT", "MEDIUM", "HEAVY", "SHIELD"],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert [item["armor_type"] for item in response.json()["armor_proficiencies"]] == [
            "LIGHT",
            "MEDIUM",
            "HEAVY",
            "SHIELD",
        ]

    async def test_gm_can_set_armor_proficiencies(self, client, gm_token, create_class):
        character_class = await create_class(name="Rogue")

        response = await client.put(
            "/classes/armor-proficiencies",
            params={"class_id": character_class.id},
            json={"armor_proficiencies": ["LIGHT"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["armor_type"] for item in response.json()["armor_proficiencies"]] == ["LIGHT"]

    async def test_set_armor_proficiencies_is_full_replace(self, client, gm_token, create_class):
        character_class = await create_class(name="Dexy")

        await client.put(
            "/classes/armor-proficiencies",
            params={"class_id": character_class.id},
            json={"armor_proficiencies": ["LIGHT", "MEDIUM"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.put(
            "/classes/armor-proficiencies",
            params={"class_id": character_class.id},
            json={"armor_proficiencies": ["SHIELD"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["armor_type"] for item in response.json()["armor_proficiencies"]] == ["SHIELD"]

    async def test_set_armor_proficiencies_duplicate_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Clumsy")

        response = await client.put(
            "/classes/armor-proficiencies",
            params={"class_id": character_class.id},
            json={"armor_proficiencies": ["LIGHT", "LIGHT"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_player_cannot_set_armor_proficiencies(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            "/classes/armor-proficiencies",
            params={"class_id": character_class.id},
            json={"armor_proficiencies": ["LIGHT"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_set_class_starting_items(self, client, gm_token, create_class, create_item):
        character_class = await create_class(name="Fighter")
        longsword = await create_item(name="Longsword", item_type="WEAPON")
        shield = await create_item(name="Shield", item_type="ARMOR")

        response = await client.put(
            "/classes/items",
            params={"class_id": character_class.id},
            json={"items": [{"item_id": longsword.id, "quantity": 1}, {"item_id": shield.id, "quantity": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [(entry["item_id"], entry["quantity"]) for entry in response.json()["starting_items"]] == [
            (longsword.id, 1),
            (shield.id, 1),
        ]

        fetched = await client.get("/classes/items", params={"class_id": character_class.id})
        assert fetched.status_code == 200
        assert [entry["item"]["name"] for entry in fetched.json()] == ["Longsword", "Shield"]

    async def test_set_class_starting_items_is_full_replace(self, client, gm_token, create_class, create_item):
        character_class = await create_class(name="Fighter")
        longsword = await create_item(name="Longsword", item_type="WEAPON")
        shortsword = await create_item(name="Shortsword", item_type="WEAPON")

        await client.put(
            "/classes/items",
            params={"class_id": character_class.id},
            json={"items": [{"item_id": longsword.id, "quantity": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.put(
            "/classes/items",
            params={"class_id": character_class.id},
            json={"items": [{"item_id": shortsword.id, "quantity": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [(entry["item_id"], entry["quantity"]) for entry in response.json()["starting_items"]] == [
            (shortsword.id, 2)
        ]

    async def test_set_class_starting_items_invalid_item_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            "/classes/items",
            params={"class_id": character_class.id},
            json={"items": [{"item_id": 9999, "quantity": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_player_cannot_set_class_starting_items(self, client, player_token, create_class, create_item):
        character_class = await create_class(name="Fighter")
        longsword = await create_item(name="Longsword", item_type="WEAPON")

        response = await client.put(
            "/classes/items",
            params={"class_id": character_class.id},
            json={"items": [{"item_id": longsword.id, "quantity": 1}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_cannot_delete_class(self, client, gm_token, create_class):
        character_class = await create_class(name="Doomed Class")

        response = await client.delete(
            f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 403
        assert (await client.get(f"/classes/{character_class.id}")).status_code == 200

    async def test_founder_can_delete_class(self, client, founder_token, create_class):
        character_class = await create_class(name="Doomed Class")

        response = await client.delete(
            f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 204
        assert (await client.get(f"/classes/{character_class.id}")).status_code == 404

    async def test_delete_class_in_use_by_character_returns_409(
        self, client, founder_token, create_class, create_user, create_character
    ):
        character_class = await create_class(name="Popular Class")
        player = await create_user()
        await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.delete(
            f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 409

    async def test_player_cannot_create_subclass(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/classes/subclasses",
            params={"class_id": character_class.id},
            json={"name": "Champion"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_subclass_and_add_features_via_endpoints(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/classes/subclasses",
            params={"class_id": character_class.id},
            json={"name": "Champion"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        subclass_id = body["id"]
        assert body["name"] == "Champion"

        for feature in [
            {"name": "Improved Critical", "level": 3},
            {"name": "Remarkable Athlete", "level": 7},
        ]:
            added = await client.post(
                "/classes/subclasses/features",
                params={"class_id": character_class.id, "subclass_id": subclass_id},
                json=feature,
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert added.status_code == 201

        fetched = await client.get(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass_id},
        )
        assert fetched.status_code == 200
        assert [item["name"] for item in fetched.json()] == [
            "Improved Critical",
            "Remarkable Athlete",
        ]

    async def test_gm_can_update_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.patch(
            "/classes/subclasses",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
            json={"name": "Renamed Champion"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Champion"

    async def test_gm_cannot_delete_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Doomed")

        response = await client.delete(
            "/classes/subclasses",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 403
        assert (
            await client.get(f"/classes/subclasses/{subclass.id}", params={"class_id": character_class.id})
        ).status_code == 200

    async def test_founder_can_delete_subclass(self, client, founder_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Doomed")

        response = await client.delete(
            "/classes/subclasses",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
            headers={"Authorization": f"Bearer {founder_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(f"/classes/subclasses/{subclass.id}", params={"class_id": character_class.id})
        ).status_code == 404

    async def test_player_cannot_add_class_feature(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/classes/features",
            params={"class_id": character_class.id},
            json={"name": "Second Wind"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_class_features(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        added = await client.post(
            "/classes/features",
            params={"class_id": character_class.id},
            json={"name": "Second Wind", "level": 1, "description": "Regain HP as a bonus action."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()
        assert feature["name"] == "Second Wind"
        assert feature["level"] == 1

        updated = await client.patch(
            "/classes/features",
            params={"class_id": character_class.id, "feature_id": feature["id"]},
            json={"description": "Regain more HP as a bonus action.", "level": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        updated_feature = updated.json()
        assert updated_feature["id"] == feature["id"]
        assert updated_feature["level"] == 2
        assert updated_feature["description"] == "Regain more HP as a bonus action."

        removed = await client.delete(
            "/classes/features",
            params={"class_id": character_class.id, "feature_id": feature["id"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        fetched = await client.get("/classes/features", params={"class_id": character_class.id})
        assert fetched.json() == []

    async def test_update_class_feature_of_another_source_returns_400(
        self, client, gm_token, create_class, create_feature
    ):
        character_class = await create_class(name="Fighter")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.patch(
            "/classes/features",
            params={"class_id": character_class.id, "feature_id": foreign.id},
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_remove_class_feature_of_another_source_returns_400(
        self, client, gm_token, create_class, create_feature
    ):
        character_class = await create_class(name="Fighter")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.delete(
            "/classes/features",
            params={"class_id": character_class.id, "feature_id": foreign.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_class_feature_endpoints_return_404(self, client, gm_token):
        assert (
            await client.post(
                "/classes/features",
                params={"class_id": 9999},
                json={"name": "Second Wind"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.patch(
                "/classes/features",
                params={"class_id": 9999, "feature_id": 1},
                json={"name": "Renamed"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.delete(
                "/classes/features",
                params={"class_id": 9999, "feature_id": 1},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404

    async def test_update_class_feature_preserves_grants_and_removal_cascades_deletes(
        self, client, gm_token, create_user, create_character, db_session
    ):
        from app.models import CharacterFeature

        created = await client.post(
            "/classes",
            json={"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        class_id = created.json()["id"]

        for feature in [
            {"name": "Second Wind", "description": "Once per short rest.", "level": 1},
            {"name": "Extra Attack", "description": "Attack twice.", "level": 5},
        ]:
            added = await client.post(
                "/classes/features",
                params={"class_id": class_id},
                json=feature,
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert added.status_code == 201

        features_response = await client.get("/classes/features", params={"class_id": class_id})
        assert features_response.status_code == 200
        features = {feature["name"]: feature for feature in features_response.json()}

        player = await create_user()
        character = await create_character(owner_id=player.id, class_id=class_id, level=11)
        kept_grant = CharacterFeature(
            character_id=character.id, feature_id=features["Extra Attack"]["id"], notes="notes"
        )
        removed_grant = CharacterFeature(
            character_id=character.id, feature_id=features["Second Wind"]["id"], notes="notes"
        )
        db_session.add_all([kept_grant, removed_grant])
        await db_session.commit()

        response = await client.patch(
            "/classes/features",
            params={"class_id": class_id, "feature_id": features["Extra Attack"]["id"]},
            json={"level": 11},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200
        assert (
            await client.delete(
                "/classes/features",
                params={"class_id": class_id, "feature_id": features["Second Wind"]["id"]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 204

        db_session.expire_all()
        assert (
            await db_session.execute(
                select(func.count())
                .select_from(CharacterFeature)
                .where(CharacterFeature.feature_id == features["Extra Attack"]["id"])
            )
        ).scalar() == 1
        assert (
            await db_session.execute(
                select(func.count())
                .select_from(CharacterFeature)
                .where(CharacterFeature.feature_id == features["Second Wind"]["id"])
            )
        ).scalar() == 0

    async def test_player_cannot_add_subclass_feature(self, client, player_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.post(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
            json={"name": "Improved Critical"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_subclass_features(
        self, client, gm_token, create_class, create_subclass
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        added = await client.post(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
            json={"name": "Improved Critical", "level": 3, "description": "Crit on 19-20."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()
        assert feature["name"] == "Improved Critical"
        assert feature["level"] == 3

        updated = await client.patch(
            "/classes/subclasses/features",
            params={
                "class_id": character_class.id,
                "subclass_id": subclass.id,
                "feature_id": feature["id"],
            },
            json={"description": "Your weapon attacks score a critical hit on a roll of 19 or 20."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        updated_feature = updated.json()
        assert updated_feature["id"] == feature["id"]
        assert updated_feature["description"] == "Your weapon attacks score a critical hit on a roll of 19 or 20."

        removed = await client.delete(
            "/classes/subclasses/features",
            params={
                "class_id": character_class.id,
                "subclass_id": subclass.id,
                "feature_id": feature["id"],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        fetched = await client.get(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass.id},
        )
        assert fetched.json() == []

    async def test_update_subclass_feature_of_another_source_returns_400(
        self, client, gm_token, create_class, create_subclass, create_feature
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.patch(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass.id, "feature_id": foreign.id},
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_remove_subclass_feature_of_another_source_returns_400(
        self, client, gm_token, create_class, create_subclass, create_feature
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.delete(
            "/classes/subclasses/features",
            params={"class_id": character_class.id, "subclass_id": subclass.id, "feature_id": foreign.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_subclass_feature_endpoints_return_404(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        assert (
            await client.post(
                "/classes/subclasses/features",
                params={"class_id": character_class.id, "subclass_id": 9999},
                json={"name": "Improved Critical"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.patch(
                "/classes/subclasses/features",
                params={"class_id": character_class.id, "subclass_id": 9999, "feature_id": 1},
                json={"name": "Renamed"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.delete(
                "/classes/subclasses/features",
                params={"class_id": character_class.id, "subclass_id": 9999, "feature_id": 1},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
