"""Tests for the class write endpoints."""

import pytest

from sqlalchemy import func, select


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassCrud:
    async def test_player_cannot_create_class(self, client, player_token):
        response = await client.post(
            "/classes/",
            json={"name": "Homebrew", "hit_dice": "D8", "spellcasting_ability": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_non_caster_class(self, client, gm_token):
        response = await client.post(
            "/classes/",
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
            "/classes/",
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

    async def test_create_class_with_nested_features(self, client, gm_token):
        response = await client.post(
            "/classes/",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "features": [
                    {"name": "Second Wind", "description": "Once per short rest."},
                    {"name": "Extra Attack", "description": "Attack twice.", "level": 5},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        class_id = response.json()["id"]

        features = (await client.get(f"/features/?source_type=CLASS&class_id={class_id}")).json()["items"]
        assert [feature["name"] for feature in features] == ["Second Wind", "Extra Attack"]
        assert all(feature["source_type"] == "CLASS" and feature["class_id"] == class_id for feature in features)
        assert {feature["name"]: feature["level"] for feature in features} == {
            "Second Wind": None,
            "Extra Attack": 5,
        }

    async def test_create_class_with_spell_slot_progression(self, client, gm_token):
        response = await client.post(
            "/classes/",
            json={
                "name": "Wizard",
                "hit_dice": "D6",
                "spellcasting_ability": "INT",
                "primary_abilities": ["INT"],
                "spell_slot_progression": [
                    {
                        "class_level": 1,
                        "slots": [{"spell_level": "CANTRIP", "slots": 3}, {"spell_level": "LEVEL_1", "slots": 2}],
                    },
                    {"class_level": 5, "slots": [{"spell_level": "LEVEL_3", "slots": 2}]},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["spell_slot_progression"] == [
            {"class_level": 1, "spell_level": "CANTRIP", "slots": 3},
            {"class_level": 1, "spell_level": "LEVEL_1", "slots": 2},
            {"class_level": 5, "spell_level": "LEVEL_3", "slots": 2},
        ]

    async def test_create_class_with_nested_subclass_and_features(self, client, gm_token):
        response = await client.post(
            "/classes/",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "subclasses": [
                    {
                        "name": "Champion",
                        "unlock_level": 3,
                        "features": [{"name": "Improved Critical", "level": 3}],
                    }
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert [item["name"] for item in body["subclasses"]] == ["Champion"]

        subclass_id = body["subclasses"][0]["id"]
        features = (await client.get(f"/features/?source_type=SUBCLASS&subclass_id={subclass_id}")).json()["items"]
        assert [item["name"] for item in features] == ["Improved Critical"]
        assert all(item["source_type"] == "SUBCLASS" and item["subclass_id"] == subclass_id for item in features)

    async def test_create_class_spellcasting_ability_not_primary_returns_400(self, client, gm_token):
        response = await client.post(
            "/classes/",
            json={"name": "Bad Caster", "hit_dice": "D8", "spellcasting_ability": "CHA"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_duplicate_class_name_returns_400(self, client, gm_token, create_class):
        await create_class(name="Fighter")
        response = await client.post(
            "/classes/",
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

    async def test_update_primary_abilities_dropping_spellcasting_ability_returns_400(self, client, gm_token, create_class):
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
            f"/classes/{character_class.id}/saving-throws",
            json={"saving_throws": ["DEX", "INT"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"] for item in response.json()["saving_throws"]} == {"DEX", "INT"}

    async def test_gm_can_set_available_skills(self, client, gm_token, create_class, create_skill):
        character_class = await create_class(name="Skillful")
        skill = await create_skill(key="PERSUASION", name="Persuasion", ability="CHA")

        response = await client.put(
            f"/classes/{character_class.id}/available-skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["available_skills"]] == [skill.id]

    async def test_gm_can_set_spell_slots(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            f"/classes/{character_class.id}/spell-slots/1",
            json={"slots": [{"spell_level": "LEVEL_1", "slots": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200

    async def test_set_spell_slots_invalid_level_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            f"/classes/{character_class.id}/spell-slots/21",
            json={"slots": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_cannot_delete_class(self, client, gm_token, create_class):
        character_class = await create_class(name="Doomed Class")

        response = await client.delete(f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/classes/{character_class.id}")).status_code == 200

    async def test_founder_can_delete_class(self, client, founder_token, create_class):
        character_class = await create_class(name="Doomed Class")

        response = await client.delete(f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/classes/{character_class.id}")).status_code == 404

    async def test_delete_class_in_use_by_character_returns_409(
        self, client, founder_token, create_class, create_user, create_character
    ):
        character_class = await create_class(name="Popular Class")
        player = await create_user()
        await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.delete(f"/classes/{character_class.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409

    async def test_player_cannot_create_subclass(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            f"/classes/{character_class.id}/subclasses",
            json={"name": "Champion"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_subclass_with_nested_features(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            f"/classes/{character_class.id}/subclasses",
            json={
                "name": "Champion",
                "unlock_level": 3,
                "features": [
                    {"name": "Improved Critical", "level": 3},
                    {"name": "Remarkable Athlete", "level": 7},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        subclass_id = body["id"]
        assert body["name"] == "Champion"
        assert body["unlock_level"] == 3
        assert [item["name"] for item in body["features"]] == ["Improved Critical", "Remarkable Athlete"]

        features = (await client.get(f"/features/?source_type=SUBCLASS&subclass_id={subclass_id}")).json()["items"]
        assert all(item["source_type"] == "SUBCLASS" and item["subclass_id"] == subclass_id for item in features)

    async def test_gm_can_update_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.patch(
            f"/classes/{character_class.id}/subclasses/{subclass.id}",
            json={"name": "Renamed Champion"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Champion"

    async def test_gm_can_delete_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Doomed")

        response = await client.delete(
            f"/classes/{character_class.id}/subclasses/{subclass.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(f"/classes/{character_class.id}/subclasses/{subclass.id}")
        ).status_code == 404

    async def test_player_cannot_replace_class_features(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            f"/classes/{character_class.id}/features",
            json={"features": [{"name": "Second Wind"}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_replace_class_features_by_id(self, client, gm_token):
        created = await client.post(
            "/classes/",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "features": [
                    {"name": "Second Wind", "description": "Once per short rest.", "level": 1},
                    {"name": "Extra Attack", "description": "Attack twice.", "level": 5},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        class_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        response = await client.put(
            f"/classes/{class_id}/features",
            json={
                "features": [
                    {"id": original["Extra Attack"], "name": "Extra Attack", "level": 11},
                    {"name": "Indomitable", "description": "Reroll a failed save.", "level": 9},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        features = {feature["name"]: feature for feature in response.json()["features"]}
        assert set(features) == {"Extra Attack", "Indomitable"}
        # Kept id → updated in place (grants survive); no id → created.
        assert features["Extra Attack"]["id"] == original["Extra Attack"]
        assert features["Extra Attack"]["level"] == 11
        assert features["Indomitable"]["level"] == 9
        # Feature absent from the payload is gone.
        assert (await client.get(f"/features/{original['Second Wind']}")).status_code == 404

    async def test_replace_class_features_unknown_id_returns_400(self, client, gm_token, create_class, create_feature):
        character_class = await create_class(name="Fighter")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.put(
            f"/classes/{character_class.id}/features",
            json={"features": [{"id": foreign.id, "name": "Alien Feature"}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_replace_class_features_duplicate_ids_returns_422(self, client, gm_token, create_class, create_feature):
        character_class = await create_class(name="Fighter")
        feature = await create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id)

        response = await client.put(
            f"/classes/{character_class.id}/features",
            json={"features": [{"id": feature.id, "name": "A"}, {"id": feature.id, "name": "B"}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_gm_can_clear_class_features(self, client, gm_token, create_class, create_feature):
        character_class = await create_class(name="Fighter")
        await create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1)

        response = await client.put(
            f"/classes/{character_class.id}/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["features"] == []

    async def test_replace_class_features_returns_404(self, client, gm_token):
        response = await client.put(
            "/classes/9999/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_replace_class_features_preserves_grants_and_cascades_deletes(
        self, client, gm_token, create_user, create_character, db_session
    ):
        from app.models import CharacterFeature

        created = await client.post(
            "/classes/",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "features": [
                    {"name": "Second Wind", "description": "Once per short rest.", "level": 1},
                    {"name": "Extra Attack", "description": "Attack twice.", "level": 5},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        class_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        player = await create_user()
        character = await create_character(owner_id=player.id, class_id=class_id, level=11)
        kept_grant = CharacterFeature(character_id=character.id, feature_id=original["Extra Attack"], notes="notes")
        removed_grant = CharacterFeature(character_id=character.id, feature_id=original["Second Wind"], notes="notes")
        db_session.add_all([kept_grant, removed_grant])
        await db_session.commit()

        response = await client.put(
            f"/classes/{class_id}/features",
            json={"features": [{"id": original["Extra Attack"], "name": "Extra Attack", "level": 11}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200

        await db_session.expire_all()
        assert (
            (
                await db_session.execute(
                    select(func.count()).select_from(CharacterFeature).where(
                        CharacterFeature.feature_id == original["Extra Attack"]
                    )
                )
            ).scalar()
            == 1
        )
        assert (
            (
                await db_session.execute(
                    select(func.count()).select_from(CharacterFeature).where(
                        CharacterFeature.feature_id == original["Second Wind"]
                    )
                )
            ).scalar()
            == 0
        )

    async def test_player_cannot_replace_subclass_features(self, client, player_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.put(
            f"/classes/{character_class.id}/subclasses/{subclass.id}/features",
            json={"features": [{"name": "Improved Critical"}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_replace_subclass_features_by_id(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        created = await client.post(
            f"/classes/{character_class.id}/subclasses",
            json={
                "name": "Champion",
                "features": [
                    {"name": "Improved Critical", "level": 3},
                    {"name": "Remarkable Athlete", "level": 7},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        subclass_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        response = await client.put(
            f"/classes/{character_class.id}/subclasses/{subclass_id}/features",
            json={
                "features": [
                    {"id": original["Improved Critical"], "name": "Improved Critical", "level": 3},
                    {"name": "Survivor", "description": "Regain HP each turn.", "level": 18},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        features = {feature["name"]: feature for feature in response.json()["features"]}
        assert set(features) == {"Improved Critical", "Survivor"}
        assert features["Improved Critical"]["id"] == original["Improved Critical"]
        assert features["Survivor"]["level"] == 18
        assert (await client.get(f"/features/{original['Remarkable Athlete']}")).status_code == 404

    async def test_replace_subclass_features_returns_404(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            f"/classes/{character_class.id}/subclasses/9999/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
