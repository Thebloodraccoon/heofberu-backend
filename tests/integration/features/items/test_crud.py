"""Tests for the item write endpoints: the core, one creation endpoint per kind, the detail PATCHes."""

import pytest

from app.constants import FeatureSourceType
from app.models.items.item_source_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestItemCrud:
    async def test_player_cannot_create_items(self, client, player_token):
        gear = await client.post("/items", json={"name": "Rope"}, headers=auth(player_token))
        weapon = await client.post("/items/weapons", json={"name": "Club"}, headers=auth(player_token))

        assert (gear.status_code, weapon.status_code) == (403, 403)

    async def test_gm_creates_one_item_of_each_kind(self, client, gm_token):
        headers = auth(gm_token)
        sword_stats = {"weapon_category": "MARTIAL", "damage_dice_count": 1, "damage_dice_type": "D8"}
        gear = await client.post("/items", json={"name": "Rope", "subtype": "ADVENTURING_GEAR"}, headers=headers)
        weapon = await client.post("/items/weapons", json={"name": "Longsword", "weapon": sword_stats}, headers=headers)
        shield_stats = {"armor_category": "SHIELD", "armor_class_base": 2}
        armor = await client.post("/items/armor", json={"name": "Shield", "armor": shield_stats}, headers=headers)
        tool = await client.post(
            "/items/tools", json={"name": "Lute", "tool": {"tool_category": "MUSICAL_INSTRUMENT"}}, headers=headers
        )

        assert [r.status_code for r in (gear, weapon, armor, tool)] == [201, 201, 201, 201]
        gear, weapon, armor, tool = (r.json() for r in (gear, weapon, armor, tool))
        assert (gear["kind"], gear["subtype"], gear["weapon"]) == ("GEAR", "ADVENTURING_GEAR", None)
        assert (weapon["kind"], weapon["weapon"]["weapon_category"], weapon["armor"]) == ("WEAPON", "MARTIAL", None)
        assert (armor["kind"], armor["armor"]["armor_category"]) == ("ARMOR", "SHIELD")
        assert (tool["kind"], tool["tool"]["tool_category"]) == ("TOOL", "MUSICAL_INSTRUMENT")

    async def test_create_duplicate_item_name_returns_409(self, client, gm_token, create_item):
        await create_item(name="Longsword")

        response = await client.post("/items/weapons", json={"name": "Longsword"}, headers=auth(gm_token))

        assert response.status_code == 409

    async def test_gm_can_update_the_core(self, client, gm_token, create_item):
        item = await create_item(name="Old Item Name")

        response = await client.patch(
            f"/items/{item.id}", json={"name": "New Item Name", "magic_bonus": 1}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert (response.json()["name"], response.json()["magic_bonus"]) == ("New Item Name", 1)

    async def test_subtype_belongs_to_gear_only(self, client, gm_token, create_item):
        weapon = await create_item(name="Club")
        gear = await create_item(name="Ring", kind="GEAR", subtype="RING")

        on_weapon = await client.patch(f"/items/{weapon.id}", json={"subtype": "RING"}, headers=auth(gm_token))
        on_gear = await client.patch(f"/items/{gear.id}", json={"subtype": "WONDROUS_ITEM"}, headers=auth(gm_token))

        assert on_weapon.status_code == 422
        assert (on_gear.status_code, on_gear.json()["subtype"]) == (200, "WONDROUS_ITEM")

    async def test_detail_patch_changes_only_the_fields_sent(self, client, gm_token, create_item):
        armor = await create_item(name="Breastplate", kind="ARMOR", armor_category="MEDIUM", armor_class_base=14)

        response = await client.patch(
            f"/items/{armor.id}/armor", json={"armor_class_max_dex_bonus": 2}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["armor"] == {
            "armor_category": "MEDIUM",
            "armor_class_base": 14,
            "armor_class_max_dex_bonus": 2,
            "strength_requirement": None,
            "stealth_disadvantage": False,
        }

    async def test_detail_patch_of_another_kind_is_409(self, client, gm_token, create_item):
        tool = await create_item(name="Lute", kind="TOOL")

        response = await client.patch(f"/items/{tool.id}/weapon", json={"range_normal": 20}, headers=auth(gm_token))

        assert response.status_code == 409

    async def test_gm_cannot_delete_item(self, client, gm_token, create_item):
        item = await create_item(name="Doomed Item")

        response = await client.delete(f"/items/{item.id}", headers=auth(gm_token))

        assert response.status_code == 403
        assert (await client.get(f"/items/{item.id}")).status_code == 200

    async def test_founder_can_delete_item(self, client, founder_token, create_item):
        item = await create_item(name="Doomed Item")

        response = await client.delete(f"/items/{item.id}", headers=auth(founder_token))

        assert response.status_code == 204
        assert (await client.get(f"/items/{item.id}")).status_code == 404

    async def test_founder_cannot_delete_item_used_only_as_choice_option(
        self, client, founder_token, db_session, create_class, create_item
    ):
        item = await create_item(name="Choice Option Item")
        character_class = await create_class(name="Fighter")

        group = SourceItemChoiceGroup(source_type=FeatureSourceType.CLASS, class_id=character_class.id, pick_count=1)
        db_session.add(group)
        await db_session.flush()
        db_session.add(SourceItemChoiceOption(group_id=group.id, item_id=item.id, quantity=1))
        await db_session.commit()

        item_id = item.id

        response = await client.delete(f"/items/{item_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/items/{item_id}")).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestItemEffects:
    AC_BONUS = [{"effect_type": "armor_class", "items": [{"value": 1}]}]

    async def _add(self, client, token, item_id, groups=None):
        return await client.post(
            f"/items/{item_id}/effects", json={"static_groups": groups or self.AC_BONUS}, headers=auth(token)
        )

    async def test_non_gm_gets_403(self, client, player_token, create_item):
        ring = await create_item(name="Ring of Protection", kind="GEAR")

        added = await self._add(client, player_token, ring.id)
        removed = await client.delete(f"/items/{ring.id}/effects/armor_class/1", headers=auth(player_token))

        assert (added.status_code, removed.status_code) == (403, 403)

    async def test_response_shape(self, client, gm_token, create_item):
        ring = await create_item(name="Ring of Protection", kind="GEAR")

        response = await self._add(client, gm_token, ring.id)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["item_id"] == ring.id
        assert [group["effect_type"] for group in body["effects"]] == ["armor_class"]
        row = body["effects"][0]["items"][0]
        assert (row["mode"], row["value"], row["allows_shield"]) == ("BONUS", 1, True)
        assert isinstance(row["id"], int)
        assert (await client.get(f"/items/{ring.id}/effects")).json() == body

    async def test_duplicate_effect_is_422(self, client, gm_token, create_item):
        ring_id = (await create_item(name="Ring of Protection", kind="GEAR")).id  # a failed request expires ORM rows
        assert (await self._add(client, gm_token, ring_id)).status_code == 200

        duplicate = await self._add(client, gm_token, ring_id)

        assert duplicate.status_code == 422
        assert len((await client.get(f"/items/{ring_id}/effects")).json()["effects"][0]["items"]) == 1

    async def test_deleting_another_items_effect_is_404(self, client, gm_token, create_item):
        ring_id = (await create_item(name="Ring of Protection", kind="GEAR")).id  # a failed request expires ORM rows
        cloak_id = (await create_item(name="Cloak of Protection", kind="GEAR")).id
        row_id = (await self._add(client, gm_token, ring_id)).json()["effects"][0]["items"][0]["id"]

        foreign = await client.delete(f"/items/{cloak_id}/effects/armor_class/{row_id}", headers=auth(gm_token))
        own = await client.delete(f"/items/{ring_id}/effects/armor_class/{row_id}", headers=auth(gm_token))

        assert foreign.status_code == 404
        assert (own.status_code, own.json()["effects"]) == (200, [])
