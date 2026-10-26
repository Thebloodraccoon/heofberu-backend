"""Tests for character item endpoints: reads are GM/owner, writes are GM-only."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterItems:
    async def test_add_and_list_item(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["item_id"] == item.id
        assert add_response.json()["quantity"] == 2

        list_response = await client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item_entry["item_id"] for item_entry in list_response.json()] == [item.id]

    async def test_add_missing_item_returns_404(self, client, gm_token, player, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_update_item_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 1},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            json={"quantity": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["quantity"] == 3

    async def test_remove_item(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                f"/characters/{character.id}/items",
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json() == []

    async def test_adding_same_item_again_merges_into_existing_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        first = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        second = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["quantity"] == 5

        list_response = await client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert len(list_response.json()) == 1
        assert list_response.json()[0]["quantity"] == 5

    async def test_player_cannot_manage_inventory_even_own_character(
        self, client, player, player_token, create_class, create_character, create_item
    ):
        """Item writes are GM-panel operations — even the owner gets a 403."""

        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 403

    async def test_owner_can_list_own_items(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        list_response = await client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert list_response.status_code == 200
        entries = list_response.json()
        assert len(entries) == 1
        assert entries[0]["item_id"] == item.id
        assert entries[0]["quantity"] == 2

    async def test_gm_can_list_any_characters_items(
        self, client, gm_token, player, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        list_response = await client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert list_response.status_code == 200
        assert [entry["item_id"] for entry in list_response.json()] == [item.id]

    async def test_other_player_cannot_list_items(
        self,
        client,
        gm_token,
        player,
        create_user,
        login_as,
        create_class,
        create_character,
        create_item,
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        other = await create_user(username="other", email="other@example.com")
        other_token = await login_as(other)

        list_response = await client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {other_token}"},
        )

        assert list_response.status_code == 403

    async def test_player_cannot_remove_item_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def give(client, gm_token, character_id, item_id):
    response = await client.post(
        f"/characters/{character_id}/gm-panel/items", json={"item_id": item_id}, headers=auth(gm_token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestEquipToggle:
    async def test_owner_equips_and_unequips_a_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        stack_id = await give(client, gm_token, character.id, (await create_item(name="Longsword")).id)
        url = f"/characters/{character.id}/items/{stack_id}"

        on = await client.patch(url, json={"is_equipped": True}, headers=auth(player_token))
        off = await client.patch(url, json={"is_equipped": False}, headers=auth(player_token))

        assert (on.status_code, on.json()["is_equipped"]) == (200, True)
        assert (off.status_code, off.json()["is_equipped"]) == (200, False)

    async def test_stranger_gets_403(
        self, client, gm_token, player, create_user, login_as, create_class, create_character, create_item
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        stack_id = await give(client, gm_token, character.id, (await create_item(name="Longsword")).id)
        stranger_token = await login_as(await create_user())

        response = await client.patch(
            f"/characters/{character.id}/items/{stack_id}", json={"is_equipped": True}, headers=auth(stranger_token)
        )

        assert response.status_code == 403

    async def test_another_characters_stack_is_404(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        fighter = await create_class(name="Fighter")
        mine = await create_character(owner_id=player.id, class_id=fighter.id, name="Mine")
        other = await create_character(owner_id=player.id, class_id=fighter.id, name="Other")
        foreign_stack = await give(client, gm_token, other.id, (await create_item(name="Longsword")).id)

        response = await client.patch(
            f"/characters/{mine.id}/items/{foreign_stack}", json={"is_equipped": True}, headers=auth(player_token)
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmAttunement:
    async def _attune(self, client, gm_token, character_id, stack_id):
        return await client.patch(
            f"/characters/{character_id}/gm-panel/items",
            params={"item_id": stack_id},
            json={"is_attuned": True},
            headers=auth(gm_token),
        )

    async def test_an_item_without_attunement_is_409(
        self, client, gm_token, player, create_class, create_character, create_item
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        stack_id = await give(client, gm_token, character.id, (await create_item(name="Longsword")).id)

        response = await self._attune(client, gm_token, character.id, stack_id)

        assert response.status_code == 409

    async def test_a_fourth_attuned_item_is_409(
        self, client, gm_token, player, create_class, create_character, create_item
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        stacks = [
            await give(
                client,
                gm_token,
                character.id,
                (await create_item(name=f"Ring {n}", kind="GEAR", requires_attunement=True)).id,
            )
            for n in range(4)
        ]

        first_three = [await self._attune(client, gm_token, character.id, stack_id) for stack_id in stacks[:3]]
        fourth = await self._attune(client, gm_token, character.id, stacks[3])

        assert [response.status_code for response in first_three] == [200, 200, 200]
        assert fourth.status_code == 409
