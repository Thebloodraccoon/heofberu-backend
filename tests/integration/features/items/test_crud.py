"""Tests for the item write endpoints."""

import pytest

from app.constants import FeatureSourceType
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption


@pytest.mark.integration
@pytest.mark.asyncio
class TestItemCrud:
    async def test_player_cannot_create_item(self, client, player_token):
        response = await client.post(
            "/items",
            json={"name": "Custom Item", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_item(self, client, gm_token):
        response = await client.post(
            "/items",
            json={"name": "Longsword", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Longsword"
        assert response.json()["item_type"] == "WEAPON"

    async def test_create_duplicate_item_name_returns_400(self, client, gm_token, create_item):
        await create_item(name="Longsword")
        response = await client.post(
            "/items",
            json={"name": "Longsword", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_update_item(self, client, gm_token, create_item):
        item = await create_item(name="Old Item Name")

        response = await client.patch(
            f"/items/{item.id}",
            json={"name": "New Item Name"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Item Name"

    async def test_gm_cannot_delete_item(self, client, gm_token, create_item):
        item = await create_item(name="Doomed Item")

        response = await client.delete(f"/items/{item.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/items/{item.id}")).status_code == 200

    async def test_founder_can_delete_item(self, client, founder_token, create_item):
        item = await create_item(name="Doomed Item")

        response = await client.delete(f"/items/{item.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/items/{item.id}")).status_code == 404

    async def test_founder_cannot_delete_item_used_only_as_choice_option(
        self, client, founder_token, db_session, create_class, create_item
    ):
        item = await create_item(name="Choice Option Item")
        character_class = await create_class(name="Fighter")

        group = SourceItemChoiceGroup(
            source_type=FeatureSourceType.CLASS, class_id=character_class.id, pick_count=1
        )
        db_session.add(group)
        await db_session.flush()
        db_session.add(SourceItemChoiceOption(group_id=group.id, item_id=item.id, quantity=1))
        await db_session.commit()

        response = await client.delete(f"/items/{item.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/items/{item.id}")).status_code == 200
