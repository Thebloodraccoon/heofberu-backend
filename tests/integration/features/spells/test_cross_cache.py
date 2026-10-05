"""A spell rename must refresh every cached payload that renders its name."""

import pytest

from app.settings import settings
from tests.helpers import set_effects


@pytest.fixture(autouse=True)
def caching_on(monkeypatch, redis_client):
    """The test stage keeps the cache off; these tests are about cached reads, so turn it on."""

    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    return redis_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def grant_spell_via_feature(client, gm_token, feature_id, spell_id):
    response = await set_effects(
        client, gm_token, feature_id, {"static_groups": [{"effect_type": "spell", "items": [{"spell_id": spell_id}]}]}
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellRenameRefreshesNameBearingCaches:
    async def test_feature_detail_summary(self, client, gm_token, create_spell, create_feature):
        spell_id = (await create_spell(name="Old Bolt")).id
        feature_id = (await create_feature(name="Gift", source_type="OTHER")).id
        await grant_spell_via_feature(client, gm_token, feature_id, spell_id)
        assert "Old Bolt" in (await client.get(f"/features/{feature_id}")).json()["effects_summary"]

        renamed = await client.patch(f"/spells/{spell_id}", json={"name": "New Bolt"}, headers=auth(gm_token))

        assert renamed.status_code == 200
        summary = (await client.get(f"/features/{feature_id}")).json()["effects_summary"]
        assert "New Bolt" in summary
        assert "Old Bolt" not in summary

    async def test_feat_detail_summary(self, client, gm_token, create_spell, create_feat):
        spell_id = (await create_spell(name="Old Ward")).id
        feat_id = (await create_feat(name="Warded")).id
        await grant_spell_via_feature(client, gm_token, feat_id, spell_id)
        assert "Old Ward" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]

        await client.patch(f"/spells/{spell_id}", json={"name": "New Ward"}, headers=auth(gm_token))

        assert "New Ward" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]

    async def test_class_feature_list_and_class_detail(self, client, gm_token, create_spell, create_class):
        spell_id = (await create_spell(name="Old Spark")).id
        class_id = (await create_class(name="Mage")).id
        created = await client.post(
            "/features",
            json={"name": "Spark", "source_type": "CLASS", "class_id": class_id, "level": 1},
            headers=auth(gm_token),
        )
        await grant_spell_via_feature(client, gm_token, created.json()["id"], spell_id)
        listed = await client.get(f"/classes/{class_id}/features")
        assert "Old Spark" in listed.json()[0]["effects_summary"]
        assert "Old Spark" in (await client.get(f"/classes/{class_id}")).text

        await client.patch(f"/spells/{spell_id}", json={"name": "New Spark"}, headers=auth(gm_token))

        assert "New Spark" in (await client.get(f"/classes/{class_id}/features")).json()[0]["effects_summary"]
        detail = (await client.get(f"/classes/{class_id}")).text
        assert "New Spark" in detail
        assert "Old Spark" not in detail

    async def test_a_description_edit_does_not_need_the_wide_purge_but_still_refreshes_spells(
        self, client, gm_token, create_spell
    ):
        spell_id = (await create_spell(name="Plain")).id
        assert (await client.get(f"/spells/{spell_id}")).json()["description"] == ""

        await client.patch(f"/spells/{spell_id}", json={"description": "Changed"}, headers=auth(gm_token))

        assert (await client.get(f"/spells/{spell_id}")).json()["description"] == "Changed"


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellListingsFollowTheEntitiesTheyName:
    """``available_*`` carry ``{id, name}`` of classes/subclasses/races/subraces: renames and deletes must reach them."""

    async def test_class_rename_refreshes_the_spell_detail_and_listing(
        self, client, gm_token, create_spell, create_class
    ):
        character_class = await create_class(name="Old Mage")
        spell = await create_spell(name="Bolt")
        await client.put(
            f"/spells/{spell.id}/classes", json={"class_ids": [character_class.id]}, headers=auth(gm_token)
        )
        assert (await client.get(f"/spells/{spell.id}")).json()["available_classes"][0]["name"] == "Old Mage"
        await client.get("/spells")

        renamed = await client.patch(
            f"/classes/{character_class.id}", json={"name": "New Mage"}, headers=auth(gm_token)
        )

        assert renamed.status_code == 200, renamed.text
        assert (await client.get(f"/spells/{spell.id}")).json()["available_classes"][0]["name"] == "New Mage"
        listing = (await client.get("/spells")).text
        assert "New Mage" in listing
        assert "Old Mage" not in listing

    async def test_class_delete_removes_it_from_the_cached_spell(
        self, client, gm_token, founder_token, create_spell, create_class
    ):
        character_class = await create_class(name="Doomed")
        spell = await create_spell(name="Bolt")
        await client.put(
            f"/spells/{spell.id}/classes", json={"class_ids": [character_class.id]}, headers=auth(gm_token)
        )
        assert len((await client.get(f"/spells/{spell.id}")).json()["available_classes"]) == 1

        deleted = await client.delete(f"/classes/{character_class.id}", headers=auth(founder_token))

        assert deleted.status_code == 204, deleted.text
        assert (await client.get(f"/spells/{spell.id}")).json()["available_classes"] == []

    async def test_subclass_rename_refreshes_the_cached_spell(
        self, client, gm_token, create_spell, create_class, create_subclass
    ):
        character_class = await create_class(name="Mage")
        subclass = await create_subclass(character_class.id, name="Old Path")
        spell = await create_spell(name="Bolt")
        await client.put(f"/spells/{spell.id}/subclasses", json={"subclass_ids": [subclass.id]}, headers=auth(gm_token))
        assert (await client.get(f"/spells/{spell.id}")).json()["available_subclasses"][0]["name"] == "Old Path"

        await client.patch(f"/subclasses/{subclass.id}", json={"name": "New Path"}, headers=auth(gm_token))

        assert (await client.get(f"/spells/{spell.id}")).json()["available_subclasses"][0]["name"] == "New Path"

    async def test_race_rename_refreshes_the_cached_spell(self, client, gm_token, create_spell, create_race):
        race = await create_race(name="Old Elf")
        spell = await create_spell(name="Bolt")
        await client.put(f"/spells/{spell.id}/races", json={"race_ids": [race.id]}, headers=auth(gm_token))
        assert (await client.get(f"/spells/{spell.id}")).json()["available_races"][0]["name"] == "Old Elf"

        await client.patch(f"/races/{race.id}", json={"name": "New Elf"}, headers=auth(gm_token))

        assert (await client.get(f"/spells/{spell.id}")).json()["available_races"][0]["name"] == "New Elf"

    async def test_race_delete_removes_it_from_the_cached_spell(
        self, client, gm_token, founder_token, create_spell, create_race
    ):
        race = await create_race(name="Doomed Elf")
        spell = await create_spell(name="Bolt")
        await client.put(f"/spells/{spell.id}/races", json={"race_ids": [race.id]}, headers=auth(gm_token))
        assert len((await client.get(f"/spells/{spell.id}")).json()["available_races"]) == 1

        deleted = await client.delete(f"/races/{race.id}", headers=auth(founder_token))

        assert deleted.status_code == 204, deleted.text
        assert (await client.get(f"/spells/{spell.id}")).json()["available_races"] == []

    async def test_subrace_rename_and_delete_refresh_the_cached_spell(
        self, client, gm_token, founder_token, create_spell, create_race, create_subrace
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race.id, name="Old Wood")
        spell = await create_spell(name="Bolt")
        await client.put(f"/spells/{spell.id}/subraces", json={"subrace_ids": [subrace.id]}, headers=auth(gm_token))
        assert (await client.get(f"/spells/{spell.id}")).json()["available_subraces"][0]["name"] == "Old Wood"

        await client.patch(f"/subraces/{subrace.id}", json={"name": "New Wood"}, headers=auth(gm_token))
        assert (await client.get(f"/spells/{spell.id}")).json()["available_subraces"][0]["name"] == "New Wood"

        await client.delete(f"/subraces/{subrace.id}", headers=auth(founder_token))
        assert (await client.get(f"/spells/{spell.id}")).json()["available_subraces"] == []
