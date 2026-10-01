"""Spell list filters, write validation (422 instead of DB errors), availability de-duplication, delete guards."""

import pytest
import pytest_asyncio

from app.models.character.character_spell_model import CharacterGrantedSpell
from app.models.features.feature_engine_models import FeatureSpellGrantEffect


def auth(token):
    return {"Authorization": f"Bearer {token}"}


PAYLOAD = {
    "name": "Frost Bolt",
    "school": "EVOCATION",
    "level": "LEVEL_1",
    "cast_time": "ACTION",
    "range_type": "RANGED",
    "range_value": 60,
    "components": ["VERBAL", "SOMATIC"],
    "duration": "INSTANTANEOUS",
    "description": "A bolt of frost.",
}


async def add_spell(client, gm_token, **overrides):
    response = await client.post("/spells", json={**PAYLOAD, **overrides}, headers=auth(gm_token))
    assert response.status_code == 201, response.text
    return response.json()


async def names(client, query):
    response = await client.get(f"/spells?{query}")
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellListFilters:
    @pytest_asyncio.fixture(autouse=True)
    async def catalog(self, client, gm_token):
        await add_spell(
            client,
            gm_token,
            name="Alpha",
            school="EVOCATION",
            level="CANTRIP",
            cast_time="ACTION",
            range_type="RANGED",
            duration="INSTANTANEOUS",
            is_ritual=False,
            is_concentration=False,
            attack_type="RANGED_ATTACK",
            damage_type="FIRE",
            damage_dice_count=1,
            damage_dice_type="D10",
        )
        await add_spell(
            client,
            gm_token,
            name="Bravo",
            school="ABJURATION",
            level="LEVEL_1",
            cast_time="REACTION",
            range_type="SELF",
            range_value=None,
            duration="ONE_ROUND",
            is_ritual=False,
            is_concentration=False,
        )
        await add_spell(
            client,
            gm_token,
            name="Charlie",
            school="DIVINATION",
            level="LEVEL_1",
            cast_time="ONE_MINUTE",
            range_type="TOUCH",
            range_value=None,
            duration="TEN_MINUTES",
            is_ritual=True,
            is_concentration=True,
        )
        await add_spell(
            client,
            gm_token,
            name="Delta",
            school="EVOCATION",
            level="LEVEL_2",
            cast_time="ACTION",
            range_type="TOUCH",
            range_value=None,
            duration="INSTANTANEOUS",
            healing_target="HP",
            healing_dice_count=2,
            healing_dice_type="D8",
        )

    async def test_school(self, client):
        assert await names(client, "school=EVOCATION") == ["Alpha", "Delta"]

    async def test_school_any_of(self, client):
        assert await names(client, "school=ABJURATION&school=DIVINATION") == ["Bravo", "Charlie"]

    async def test_cast_time(self, client):
        assert await names(client, "cast_time=REACTION") == ["Bravo"]

    async def test_range_type(self, client):
        assert await names(client, "range_type=TOUCH") == ["Charlie", "Delta"]

    async def test_duration(self, client):
        assert await names(client, "duration=TEN_MINUTES") == ["Charlie"]

    async def test_attack_type(self, client):
        assert await names(client, "attack_type=RANGED_ATTACK") == ["Alpha"]

    async def test_damage_type(self, client):
        assert await names(client, "damage_type=FIRE") == ["Alpha"]

    async def test_healing_target(self, client):
        assert await names(client, "healing_target=HP") == ["Delta"]

    async def test_is_ritual(self, client):
        assert await names(client, "is_ritual=true") == ["Charlie"]
        assert await names(client, "is_ritual=false") == ["Alpha", "Bravo", "Delta"]

    async def test_is_concentration(self, client):
        assert await names(client, "is_concentration=true") == ["Charlie"]

    async def test_filters_combine_with_and(self, client):
        assert await names(client, "school=EVOCATION&level=LEVEL_2") == ["Delta"]

    async def test_search_is_case_insensitive_substring(self, client):
        assert await names(client, "search=ARL") == ["Charlie"]

    async def test_pagination_total_and_stable_order(self, client):
        first = (await client.get("/spells?size=3&page=1")).json()
        second = (await client.get("/spells?size=3&page=2")).json()

        assert first["total"] == 4
        assert [item["name"] for item in first["items"]] == ["Alpha", "Bravo", "Charlie"]
        assert [item["name"] for item in second["items"]] == ["Delta"]

    async def test_invalid_enum_filter_is_422(self, client):
        assert (await client.get("/spells?school=NOPE")).status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellWriteValidation:
    async def test_name_over_the_column_limit_is_422(self, client, gm_token):
        response = await client.post("/spells", json={**PAYLOAD, "name": "x" * 301}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_unknown_key_is_422(self, client, gm_token):
        response = await client.post("/spells", json={**PAYLOAD, "lvl": 3}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_dice_count_without_dice_type_is_422(self, client, gm_token):
        response = await client.post("/spells", json={**PAYLOAD, "damage_dice_count": 3}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_material_text_without_material_component_is_422(self, client, gm_token):
        response = await client.post("/spells", json={**PAYLOAD, "material": "a feather"}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_with_null_for_a_required_column_is_422_and_keeps_the_row(self, client, gm_token):
        spell = await add_spell(client, gm_token, name="Keeper")

        response = await client.patch(f"/spells/{spell['id']}", json={"school": None}, headers=auth(gm_token))

        assert response.status_code == 422
        assert (await client.get(f"/spells/{spell['id']}")).json()["school"] == "EVOCATION"

    async def test_patch_can_clear_a_nullable_column(self, client, gm_token):
        spell = await add_spell(client, gm_token, name="Ranged", range_value=30)

        response = await client.patch(f"/spells/{spell['id']}", json={"range_value": None}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["range_value"] is None

    async def test_patch_with_a_typo_is_422(self, client, gm_token):
        spell = await add_spell(client, gm_token, name="Typo")

        response = await client.patch(f"/spells/{spell['id']}", json={"nmae": "x"}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_to_an_existing_name_is_400(self, client, gm_token):
        await add_spell(client, gm_token, name="Taken")
        spell = await add_spell(client, gm_token, name="Free")

        response = await client.patch(f"/spells/{spell['id']}", json={"name": "Taken"}, headers=auth(gm_token))

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestAvailabilityDeduplication:
    async def test_repeated_class_ids_on_create_are_collapsed(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard")

        spell = await add_spell(client, gm_token, name="Dup Create", available_classes=[character_class.id] * 3)

        assert [item["id"] for item in spell["available_classes"]] == [character_class.id]

    async def test_repeated_ids_on_put_are_collapsed_instead_of_a_primary_key_error(
        self, client, gm_token, create_spell, create_class, create_race
    ):
        spell = await create_spell(name="Dup Put")
        character_class = await create_class(name="Cleric")
        race = await create_race(name="Gnome")
        spell_id = spell.id

        classes = await client.put(
            f"/spells/{spell_id}/classes",
            json={"class_ids": [character_class.id, character_class.id]},
            headers=auth(gm_token),
        )
        races = await client.put(
            f"/spells/{spell_id}/races", json={"race_ids": [race.id, race.id]}, headers=auth(gm_token)
        )

        assert classes.status_code == 200
        assert [item["id"] for item in classes.json()["available_classes"]] == [character_class.id]
        assert races.status_code == 200
        assert [item["id"] for item in races.json()["available_races"]] == [race.id]

    async def test_a_rejected_put_keeps_the_previous_links(self, client, gm_token, create_spell, create_class):
        spell = await create_spell(name="Stays Put")
        character_class = await create_class(name="Bard")
        spell_id = spell.id
        await client.put(
            f"/spells/{spell_id}/classes", json={"class_ids": [character_class.id]}, headers=auth(gm_token)
        )

        response = await client.put(
            f"/spells/{spell_id}/classes", json={"class_ids": [character_class.id, 999999]}, headers=auth(gm_token)
        )

        assert response.status_code == 400
        assert [item["id"] for item in (await client.get(f"/spells/{spell_id}")).json()["available_classes"]] == [
            character_class.id
        ]

    async def test_put_availability_refreshes_the_cached_listing(self, client, gm_token, create_spell, create_class):
        spell = await create_spell(name="Cached Listing")
        character_class = await create_class(name="Ranger")
        spell_id = spell.id
        before = (await client.get("/spells?search=Cached")).json()["items"][0]
        assert before["available_classes"] == []

        await client.put(
            f"/spells/{spell_id}/classes", json={"class_ids": [character_class.id]}, headers=auth(gm_token)
        )

        after = (await client.get("/spells?search=Cached")).json()["items"][0]
        assert [item["name"] for item in after["available_classes"]] == ["Ranger"]

    async def test_listing_orders_availability_by_name(self, client, gm_token, create_spell, create_class):
        spell = await create_spell(name="Ordered")
        zed = await create_class(name="Zed")
        abe = await create_class(name="Abe")
        spell_id = spell.id
        await client.put(f"/spells/{spell_id}/classes", json={"class_ids": [zed.id, abe.id]}, headers=auth(gm_token))

        item = (await client.get("/spells?search=Ordered")).json()["items"][0]

        assert [ref["name"] for ref in item["available_classes"]] == ["Abe", "Zed"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteSpellGuards:
    async def test_spell_granted_by_a_feature_effect_cannot_be_deleted(
        self, client, founder_token, create_spell, create_feature, db_session
    ):
        spell = await create_spell(name="Granted By Feature")
        feature = await create_feature(name="Gift", source_type="OTHER")
        spell_id = spell.id
        db_session.add(FeatureSpellGrantEffect(feature_id=feature.id, spell_id=spell_id))
        await db_session.commit()

        response = await client.delete(f"/spells/{spell_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/spells/{spell_id}")).status_code == 200

    async def test_spell_granted_to_a_character_by_the_gm_cannot_be_deleted(
        self, client, founder_token, create_spell, create_class, create_character, create_user, db_session
    ):
        spell = await create_spell(name="GM Granted")
        player = await create_user()
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Druid")).id)
        spell_id = spell.id
        db_session.add(CharacterGrantedSpell(character_id=character.id, spell_id=spell_id))
        await db_session.commit()

        response = await client.delete(f"/spells/{spell_id}", headers=auth(founder_token))

        assert response.status_code == 409

    async def test_deleting_a_spell_removes_its_availability_links_and_refreshes_the_listing(
        self, client, gm_token, founder_token, create_class
    ):
        character_class = await create_class(name="Paladin")
        spell = await add_spell(client, gm_token, name="Gone Soon", available_classes=[character_class.id])
        assert await names(client, "search=Gone") == ["Gone Soon"]

        assert (await client.delete(f"/spells/{spell['id']}", headers=auth(founder_token))).status_code == 204

        assert await names(client, "search=Gone") == []

    async def test_delete_unknown_spell_is_404(self, client, founder_token):
        assert (await client.delete("/spells/987654", headers=auth(founder_token))).status_code == 404
