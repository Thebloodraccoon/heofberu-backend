"""End-to-end tests for starting-equipment "pick N of M" choices at character creation."""

import pytest

from app.constants import FeatureSourceType
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption


async def set_class_equipment(client, gm_token, class_id, items):
    response = await client.put(
        f"/classes/{class_id}/items",
        json={"items": items},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text


async def set_class_choice_groups(client, gm_token, class_id, groups):
    response = await client.put(
        f"/classes/{class_id}/choice-groups",
        json={"choice_groups": groups},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["choice_groups"]


async def create_character_with_choices(client, player_token, class_id, item_choice_ids, background_id=None):
    payload = {"name": "Raistlin", "class_id": class_id}
    if background_id is not None:
        payload["background_id"] = background_id
    if item_choice_ids is not None:
        payload["item_choice_ids"] = item_choice_ids
    return await client.post("/characters", json=payload, headers={"Authorization": f"Bearer {player_token}"})


async def get_character_items(client, token, character_id):
    response = await client.get(
        f"/characters/{character_id}/gm-panel/items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return {entry["item_id"]: entry["quantity"] for entry in response.json()}


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassItemChoicesAtCreation:
    async def test_creation_grants_chosen_alternative_and_guaranteed_item(
        self, client, player_token, gm_token, create_class, create_item
    ):
        character_class = await create_class(name="Fighter")
        dagger = await create_item(name="Dagger")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        await set_class_equipment(client, gm_token, character_class.id, [{"item_id": dagger.id, "quantity": 1}])
        groups = await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [
                {
                    "pick_count": 1,
                    "options": [
                        {"item_id": sword.id, "quantity": 1},
                        {"item_id": staff.id, "quantity": 1},
                    ],
                }
            ],
        )
        sword_option = next(option for option in groups[0]["options"] if option["item_id"] == sword.id)

        response = await create_character_with_choices(
            client, player_token, character_class.id, [sword_option["id"]]
        )

        assert response.status_code == 201, response.text
        items = await get_character_items(client, player_token, response.json()["id"])
        # The guaranteed dagger plus exactly the chosen alternative — the
        # side of the choice the player did NOT pick is never granted.
        assert items == {dagger.id: 1, sword.id: 1}

    async def test_creation_choosing_the_other_option_grants_it_instead(
        self, client, player_token, gm_token, create_class, create_item
    ):
        character_class = await create_class(name="Fighter")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        groups = await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [{"pick_count": 1, "options": [{"item_id": sword.id}, {"item_id": staff.id}]}],
        )
        staff_option = next(option for option in groups[0]["options"] if option["item_id"] == staff.id)

        response = await create_character_with_choices(client, player_token, character_class.id, [staff_option["id"]])

        assert response.status_code == 201, response.text
        items = await get_character_items(client, player_token, response.json()["id"])
        assert items == {staff.id: 1}

    async def test_choice_group_must_be_answered_exactly_pick_count(
        self, client, player_token, gm_token, create_class, create_item
    ):
        character_class = await create_class(name="Fighter")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        groups = await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [{"pick_count": 1, "options": [{"item_id": sword.id}, {"item_id": staff.id}]}],
        )
        sword_option = next(option for option in groups[0]["options"] if option["item_id"] == sword.id)
        staff_option = next(option for option in groups[0]["options"] if option["item_id"] == staff.id)

        # Omitted choice: the group is left unanswered.
        missing = await create_character_with_choices(client, player_token, character_class.id, [])
        assert missing.status_code == 400, missing.text

        # Over-answering a pick-1 group: more options than pick_count.
        over = await create_character_with_choices(
            client, player_token, character_class.id, [sword_option["id"], staff_option["id"]]
        )
        assert over.status_code == 400, over.text

    async def test_foreign_or_duplicate_choice_is_rejected(
        self, client, player_token, gm_token, create_class, create_item
    ):
        character_class = await create_class(name="Fighter")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [{"pick_count": 1, "options": [{"item_id": sword.id}, {"item_id": staff.id}]}],
        )

        foreign = await create_character_with_choices(client, player_token, character_class.id, [999999])
        assert foreign.status_code == 400, foreign.text

        duplicate = await create_character_with_choices(client, player_token, character_class.id, [1, 1])
        assert duplicate.status_code == 422, duplicate.text

    async def test_choice_without_any_choice_group_is_rejected(
        self, client, player_token, create_class
    ):
        character_class = await create_class(name="Fighter")

        response = await create_character_with_choices(client, player_token, character_class.id, [12345])

        assert response.status_code == 400, response.text

    async def test_chosen_option_quantity_is_granted(self, client, player_token, gm_token, create_class, create_item):
        character_class = await create_class(name="Fighter")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        groups = await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [{"pick_count": 1, "options": [{"item_id": sword.id, "quantity": 3}, {"item_id": staff.id}]}],
        )
        sword_option = next(option for option in groups[0]["options"] if option["item_id"] == sword.id)

        response = await create_character_with_choices(client, player_token, character_class.id, [sword_option["id"]])

        assert response.status_code == 201, response.text
        items = await get_character_items(client, player_token, response.json()["id"])
        assert items == {sword.id: 3}

    async def test_overlapping_guaranteed_and_chosen_item_merge_into_one_stack(
        self, client, player_token, gm_token, create_class, create_item
    ):
        character_class = await create_class(name="Fighter")
        sword = await create_item(name="Longsword")
        staff = await create_item(name="Staff")

        await set_class_equipment(client, gm_token, character_class.id, [{"item_id": sword.id, "quantity": 1}])
        groups = await set_class_choice_groups(
            client,
            gm_token,
            character_class.id,
            [{"pick_count": 1, "options": [{"item_id": sword.id, "quantity": 2}, {"item_id": staff.id}]}],
        )
        sword_option = next(option for option in groups[0]["options"] if option["item_id"] == sword.id)

        response = await create_character_with_choices(client, player_token, character_class.id, [sword_option["id"]])

        assert response.status_code == 201, response.text
        items = await get_character_items(client, player_token, response.json()["id"])
        assert items == {sword.id: 3}


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundItemChoices:
    async def test_creation_with_background_choice_group_requires_and_grants_the_choice(
        self, client, player_token, gm_token, create_class, create_background, create_item, db_session
    ):
        character_class = await create_class(name="Fighter")
        background = await create_background(name="Entertainer")
        vest = await create_item(name="Vest")
        lute_item = await create_item(name="Lute")

        group = SourceItemChoiceGroup(
            source_type=FeatureSourceType.BACKGROUND, background_id=background.id, pick_count=1
        )
        db_session.add(group)
        await db_session.flush()
        vest_option = SourceItemChoiceOption(group_id=group.id, item_id=vest.id, quantity=1)
        lute_option = SourceItemChoiceOption(group_id=group.id, item_id=lute_item.id, quantity=1)
        db_session.add(vest_option)
        db_session.add(lute_option)
        await db_session.commit()

        missing = await create_character_with_choices(
            client, player_token, character_class.id, [], background_id=background.id
        )
        assert missing.status_code == 400, missing.text

        response = await create_character_with_choices(
            client, player_token, character_class.id, [vest_option.id], background_id=background.id
        )
        assert response.status_code == 201, response.text
        items = await get_character_items(client, player_token, response.json()["id"])
        assert items == {vest.id: 1}

    async def test_setting_background_with_choice_groups_after_creation_returns_400(
        self, client, player, player_token, gm_token, db_session, create_class, create_character, create_background, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        background = await create_background(name="Noble")
        rapier = await create_item(name="Rapier")

        group = SourceItemChoiceGroup(
            source_type=FeatureSourceType.BACKGROUND, background_id=background.id, pick_count=1
        )
        db_session.add(group)
        await db_session.flush()
        db_session.add(SourceItemChoiceOption(group_id=group.id, item_id=rapier.id, quantity=1))
        await db_session.commit()

        response = await client.patch(
            f"/characters/{character.id}/progression/background",
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400, response.text

        detail = await client.get(
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert detail.status_code == 200
        assert detail.json()["background_id"] is None