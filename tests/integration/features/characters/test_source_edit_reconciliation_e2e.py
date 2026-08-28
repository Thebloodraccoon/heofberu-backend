"""
End-to-end source-edit reconciliation: a GM edits a catalog source (race or
class — adds/removes features, attaches fixed ability-score effects) and the
affected characters reconcile their auto-granted feature rows and refresh
their stat caches in the same transaction, with no character-side write.
"""

import pytest


async def feature_ids(client, character_id, token):
    response = await client.get(
        "/characters/features",
        params={"character_id": character_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return {entry["feature"]["name"] for entry in response.json()}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSourceEditReconciliation:
    async def test_race_feature_add_grants_and_remove_revokes_on_existing_character(
        self, client, player, create_class, create_api_character, create_race, gm_token
    ):
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Dwarf")
        character, token = await create_api_character(class_id=character_class.id, owner=player, race_id=race.id)

        assert await feature_ids(client, character["id"], token) == set()

        add_response = await client.post(
            "/features",
            json={"name": "Stonecunning", "description": "Stone sense.", "source_type": "RACE", "race_id": race.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201, add_response.text

        assert await feature_ids(client, character["id"], token) == {"Stonecunning"}

        remove_response = await client.delete(
            f"/features/{add_response.json()['id']}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_response.status_code == 204

        assert await feature_ids(client, character["id"], token) == set()

    async def test_new_class_feature_at_current_level_is_auto_granted(
        self, client, player, create_class, create_api_character, gm_token
    ):
        character_class = await create_class(name="Barbarian")
        character, token = await create_api_character(class_id=character_class.id, owner=player)

        add_response = await client.post(
            "/features",
            json={
                "name": "Rage",
                "description": "Bonus damage.",
                "level": 1,
                "source_type": "CLASS",
                "class_id": character_class.id,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201, add_response.text

        names = await feature_ids(client, character["id"], token)
        assert names == {"Rage"}

    async def test_feature_ability_increase_recalculates_character_stats_without_character_write(
        self, client, player, create_class, create_api_character, gm_token, db_session
    ):
        from sqlalchemy import select

        from app.models import CharacterAbilityScore

        character_class = await create_class(name="Wizard", spellcasting_ability=None)
        character, token = await create_api_character(class_id=character_class.id, owner=player)

        before_response = await client.get(
            f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"}
        )
        assert before_response.status_code == 200
        assert before_response.json()["ability_scores"]["intelligence_total"] == 10

        add_response = await client.post(
            "/features",
            json={
                "name": "Arcane Aptitude",
                "description": "+2 INT.",
                "level": 1,
                "source_type": "CLASS",
                "class_id": character_class.id,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201, add_response.text
        feature_id = add_response.json()["id"]

        increases_response = await client.put(
            "/features/ability-increases",
            params={"feature_id": feature_id},
            json={"ability_increases": [{"ability": "INT", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert increases_response.status_code == 200, increases_response.text

        after_response = await client.get(
            f"/characters/{character['id']}", headers={"Authorization": f"Bearer {token}"}
        )
        assert after_response.status_code == 200
        assert after_response.json()["ability_scores"]["intelligence_total"] == 12

        cached = (
            await db_session.execute(
                select(CharacterAbilityScore).where(CharacterAbilityScore.character_id == character["id"])
            )
        ).scalar_one()
        assert cached.intelligence_total == 12
