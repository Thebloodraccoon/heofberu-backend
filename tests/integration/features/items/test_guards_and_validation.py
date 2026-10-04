"""Item validation, delete guards (incl. cascading proficiencies) and cache invalidation."""

import pytest

from app.models import CharacterProficiency
from app.settings import settings


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestValidation:
    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    async def test_create_rejects_bad_names(self, client, gm_token, name):
        response = await client.post("/items", json={"name": name, "item_type": "WEAPON"}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "extra",
        [
            {"weight": -1},
            {"weight": "10000.00"},
            {"weight": "1.234"},
            {"cost_gold": -5},
            {"cost_gold": "100000000000"},
            {"damage_dice_count": 0},
            {"damage_dice_count": 2**40},
            {"armor_class_base": -1},
            {"armor_class_max_dex_bonus": -1},
            {"strength_requirement": 99},
            {"weapon_properties": "x" * 301},
        ],
    )
    async def test_create_rejects_out_of_range_values(self, client, gm_token, extra):
        response = await client.post(
            "/items", json={"name": "Odd", "item_type": "WEAPON", **extra}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_create_accepts_the_documented_boundaries(self, client, gm_token):
        response = await client.post(
            "/items",
            json={"name": "Heavy Thing", "item_type": "ARMOR", "weight": "9999.99", "cost_gold": "99999999.99"},
            headers=auth(gm_token),
        )

        assert response.status_code == 201

    @pytest.mark.parametrize("field", ["name", "item_type", "rarity", "requires_attunement", "description"])
    async def test_patch_rejects_explicit_null_for_required_fields(self, client, gm_token, create_item, field):
        item = await create_item(name="Longsword")

        response = await client.patch(f"/items/{item.id}", json={field: None}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_can_clear_nullable_fields(self, client, gm_token, create_item):
        item = await create_item(name="Longsword")
        await client.patch(f"/items/{item.id}", json={"weight": "3", "cost_gold": "15"}, headers=auth(gm_token))

        response = await client.patch(f"/items/{item.id}", json={"weight": None}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["weight"] is None
        assert response.json()["cost_gold"] is not None

    async def test_patch_to_existing_name_returns_400(self, client, gm_token, create_item):
        await create_item(name="Longsword")
        other = await create_item(name="Dagger")

        response = await client.patch(f"/items/{other.id}", json={"name": "Longsword"}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_documented_create_examples_are_valid(self, client, gm_token):
        weapon = await client.post(
            "/items",
            json={
                "name": "Longsword",
                "item_type": "WEAPON",
                "rarity": "NONE",
                "weight": 3,
                "cost_gold": 15,
                "damage_dice_count": 1,
                "damage_dice_type": "D8",
                "damage_type": "SLASHING",
                "weapon_properties": "VERSATILE",
            },
            headers=auth(gm_token),
        )
        armor = await client.post(
            "/items",
            json={
                "name": "Chain Mail",
                "item_type": "ARMOR",
                "weight": 55,
                "cost_gold": 75,
                "armor_class_base": 16,
                "armor_class_dex_bonus": False,
                "strength_requirement": 13,
                "stealth_disadvantage": True,
            },
            headers=auth(gm_token),
        )

        assert (weapon.status_code, armor.status_code) == (201, 201)


@pytest.mark.integration
@pytest.mark.asyncio
class TestListing:
    async def test_filters_by_type_rarity_and_search(self, client, create_item):
        await create_item(name="Longsword", item_type="WEAPON", rarity="NONE")
        await create_item(name="Longbow", item_type="WEAPON", rarity="RARE")
        await create_item(name="Chain Mail", item_type="ARMOR", rarity="NONE")

        weapons = await client.get("/items", params={"item_type": ["WEAPON"]})
        rare_weapons = await client.get("/items", params={"item_type": ["WEAPON"], "rarity": ["RARE"]})
        searched = await client.get("/items", params={"search": "long"})
        both_types = await client.get("/items", params={"item_type": ["WEAPON", "ARMOR"]})

        assert {item["name"] for item in weapons.json()["items"]} == {"Longsword", "Longbow"}
        assert [item["name"] for item in rare_weapons.json()["items"]] == ["Longbow"]
        assert {item["name"] for item in searched.json()["items"]} == {"Longsword", "Longbow"}
        assert both_types.json()["total"] == 3

    async def test_search_longer_than_limit_returns_422(self, client):
        assert (await client.get("/items", params={"search": "x" * 101})).status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteGuards:
    async def test_delete_blocked_when_a_character_holds_a_proficiency_in_it(
        self, client, founder_token, db_session, player, create_item, create_class, create_character
    ):
        item = await create_item(name="Longsword")
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        item_id = item.id
        db_session.add(
            CharacterProficiency(
                character_id=character.id,
                proficiency_type="WEAPON",
                item_id=item_id,
                source_type="GM",
                action="GRANT",
            )
        )
        await db_session.commit()

        response = await client.delete(f"/items/{item_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/items/{item_id}")).status_code == 200

    async def test_delete_blocked_when_a_feature_effect_references_it(
        self, client, founder_token, gm_token, create_item, create_feat
    ):
        item = await create_item(name="Longsword")
        feat = await create_feat(name="Weapon Master")
        item_id = item.id
        put = await client.put(
            f"/feats/{feat.id}/effects",
            json={"static_groups": [{"effect_type": "weapon", "items": [{"item_id": item_id}]}]},
            headers=auth(gm_token),
        )
        assert put.status_code == 200

        response = await client.delete(f"/items/{item_id}", headers=auth(founder_token))

        assert response.status_code == 409

    async def test_delete_blocked_when_it_is_background_starting_equipment(
        self, client, founder_token, gm_token, create_item, create_background
    ):
        item = await create_item(name="Censer")
        background = await create_background(name="Acolyte")
        item_id = item.id
        await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": [{"item_id": item_id, "quantity": 1}]},
            headers=auth(gm_token),
        )

        response = await client.delete(f"/items/{item_id}", headers=auth(founder_token))

        assert response.status_code == 409

    async def test_delete_missing_item_returns_404(self, client, founder_token):
        assert (await client.delete("/items/999999", headers=auth(founder_token))).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheInvalidation:
    async def test_rename_refreshes_starting_equipment_and_feature_summaries(
        self, client, gm_token, create_item, create_background, create_feat, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        item = await create_item(name="Censer")
        background = await create_background(name="Acolyte")
        feat = await create_feat(name="Weapon Master")
        item_id, background_id, feat_id = item.id, background.id, feat.id
        await client.put(
            f"/backgrounds/{background_id}/items",
            json={"items": [{"item_id": item_id, "quantity": 1}]},
            headers=auth(gm_token),
        )
        await client.put(
            f"/feats/{feat_id}/effects",
            json={"static_groups": [{"effect_type": "weapon", "items": [{"item_id": item_id}]}]},
            headers=auth(gm_token),
        )

        assert (await client.get(f"/backgrounds/{background_id}/items")).json()[0]["item"]["name"] == "Censer"
        assert "Censer" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]

        await client.patch(f"/items/{item_id}", json={"name": "Thurible"}, headers=auth(gm_token))

        assert (await client.get(f"/backgrounds/{background_id}/items")).json()[0]["item"]["name"] == "Thurible"
        assert (await client.get(f"/backgrounds/{background_id}")).json()["starting_items"][0]["item"][
            "name"
        ] == "Thurible"
        assert "Thurible" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]

    async def test_equipment_listings_of_a_class_and_a_background_with_the_same_id_do_not_collide(
        self, client, gm_token, create_item, create_class, create_background, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        sword = await create_item(name="Sword")
        lamp = await create_item(name="Lamp")
        character_class = await create_class(name="Fighter")
        background = await create_background(name="Sage")
        assert character_class.id == background.id
        await client.put(
            f"/classes/{character_class.id}/items",
            json={"items": [{"item_id": sword.id, "quantity": 1}]},
            headers=auth(gm_token),
        )
        await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": [{"item_id": lamp.id, "quantity": 1}]},
            headers=auth(gm_token),
        )

        for _ in range(2):
            class_items = (await client.get(f"/classes/{character_class.id}/items")).json()
            background_items = (await client.get(f"/backgrounds/{background.id}/items")).json()

            assert [entry["item"]["name"] for entry in class_items] == ["Sword"]
            assert [entry["item"]["name"] for entry in background_items] == ["Lamp"]

    async def test_rename_refreshes_race_and_subrace_details_naming_the_item(
        self, client, gm_token, create_item, create_race, create_subrace, create_feature, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        item = await create_item(name="Pike")
        race = await create_race(name="Dwarf")
        subrace = await create_subrace(race.id, name="Hill")
        race_feature = await create_feature(name="Pike Training", source_type="RACE", race_id=race.id)
        subrace_feature = await create_feature(name="Hill Training", source_type="SUBRACE", subrace_id=subrace.id)
        for feature_id in (race_feature.id, subrace_feature.id):
            await client.put(
                f"/features/{feature_id}/effects",
                json={"static_groups": [{"effect_type": "weapon", "items": [{"item_id": item.id}]}]},
                headers=auth(gm_token),
            )
        assert "Pike" in (await client.get(f"/races/{race.id}")).text
        assert "Pike" in (await client.get(f"/subraces/{subrace.id}")).text

        await client.patch(f"/items/{item.id}", json={"name": "Halberd"}, headers=auth(gm_token))

        race_detail = (await client.get(f"/races/{race.id}")).text
        subrace_detail = (await client.get(f"/subraces/{subrace.id}")).text
        assert "Halberd" in race_detail and 'Pike"' not in race_detail
        assert "Halberd" in subrace_detail and 'Pike"' not in subrace_detail

    async def test_create_purges_only_the_item_listing(
        self, client, gm_token, create_background, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        background = await create_background(name="Acolyte")
        await client.get(f"/backgrounds/{background.id}")
        await client.get("/items")
        prefix = settings.CACHE_PREFIX

        created = await client.post("/items", json={"name": "Brand New", "item_type": "WEAPON"}, headers=auth(gm_token))

        assert created.status_code == 201
        assert await redis_client.keys(f"{prefix}:items:*") == []
        assert await redis_client.keys(f"{prefix}:backgrounds:*") != []
        assert "Brand New" in {item["name"] for item in (await client.get("/items")).json()["items"]}
