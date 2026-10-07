"""Tests for the point-write endpoints of /features/{id}: fixed effects, choice groups, options and option effects."""

import pytest
from sqlalchemy import func, select

from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from tests.helpers import effect_items


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def static_items(body, effect_type):
    """Items of one ``effect_type`` group in a ``FeatureEffectsResponse``, or ``[]``."""

    return effect_items(body["static_groups"], effect_type)


async def add_effects(client, token, feature_id, static_groups):
    return await client.post(
        f"/features/{feature_id}/effects", json={"static_groups": static_groups}, headers=auth(token)
    )


async def add_group(client, token, feature_id, payload):
    return await client.post(f"/features/{feature_id}/choice-groups", json=payload, headers=auth(token))


def skill_option(skill_id):
    return {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]}


@pytest.mark.integration
@pytest.mark.asyncio
class TestAddFixedEffects:
    async def test_adds_new_rows_and_keeps_existing_ones(self, client, gm_token, create_feature):
        feature = await create_feature(name="Heavy Armor Master")

        first = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "armor", "items": [{"armor_type": "MEDIUM"}]}]
        )
        second = await add_effects(
            client,
            gm_token,
            feature.id,
            [
                {"effect_type": "armor", "items": [{"armor_type": "HEAVY"}]},
                {"effect_type": "saving_throw", "items": [{"ability": "DEX"}]},
            ],
        )

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        body = second.json()
        assert {item["armor_type"] for item in static_items(body, "armor")} == {"MEDIUM", "HEAVY"}
        assert [item["ability"] for item in static_items(body, "saving_throw")] == ["DEX"]
        assert (await client.get(f"/features/{feature.id}/effects")).json() == body

    async def test_empty_payload_changes_nothing(self, client, gm_token, create_feature):
        feature = await create_feature(name="Nothing")

        response = await add_effects(client, gm_token, feature.id, [])

        assert response.status_code == 201
        assert response.json()["static_groups"] == []

    async def test_item_with_an_id_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Has Id")

        response = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "armor", "items": [{"id": 5, "armor_type": "LIGHT"}]}]
        )

        assert response.status_code == 422

    async def test_unknown_skill_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Ghost Skill")

        response = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "skill", "items": [{"skill_id": 999999}]}]
        )

        assert response.status_code == 422

    async def test_fixed_skill_without_skill_id_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Open Skill")

        response = await add_effects(client, gm_token, feature.id, [{"effect_type": "skill", "items": [{}]}])

        assert response.status_code == 422

    async def test_removed_spell_fields_are_rejected(self, client, gm_token, create_feature, create_spell):
        feature = await create_feature(name="Old Spell Form")
        spell = await create_spell(name="Light")

        response = await add_effects(
            client,
            gm_token,
            feature.id,
            [{"effect_type": "spell", "items": [{"spell_id": spell.id, "always_prepared": True}]}],
        )

        assert response.status_code == 422

    async def test_unknown_feature_returns_404(self, client, gm_token):
        response = await add_effects(client, gm_token, 999999, [])

        assert response.status_code == 404

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")

        response = await add_effects(
            client, player_token, feature.id, [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdateFixedEffect:
    async def test_patch_changes_only_the_sent_fields_in_place(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Expert")
        skill = await create_skill(name="Stealth", ability="DEX")
        created = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]
        )
        row = static_items(created.json(), "skill")[0]
        assert row["grants_expertise"] is False

        response = await client.patch(
            f"/features/{feature.id}/effects/skill/{row['id']}", json={"grants_expertise": True}, headers=auth(gm_token)
        )

        assert response.status_code == 200, response.text
        assert static_items(response.json(), "skill") == [
            {"id": row["id"], "skill_id": skill.id, "grants_expertise": True}
        ]

    async def test_patch_ability_amount(self, client, gm_token, create_feature):
        feature = await create_feature(name="Bigger Boost")
        created = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]
        )
        row_id = static_items(created.json(), "ability")[0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/effects/ability/{row_id}",
            json={"amount": 2, "new_cap": 22},
            headers=auth(gm_token),
        )

        assert response.status_code == 200, response.text
        item = static_items(response.json(), "ability")[0]
        assert (item["ability"], item["amount"], item["new_cap"]) == ("STR", 2, 22)

    @pytest.mark.parametrize(
        "changes",
        [{"amount": 99}, {"bogus": 1}, {"new_cap": 5}],
        ids=["out-of-range", "unknown-key", "bad-cap"],
    )
    async def test_invalid_change_returns_422_and_keeps_the_row(self, client, gm_token, create_feature, changes):
        feature = await create_feature(name="Strict")
        created = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]
        )
        row_id = static_items(created.json(), "ability")[0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/effects/ability/{row_id}", json=changes, headers=auth(gm_token)
        )

        assert response.status_code == 422
        after = (await client.get(f"/features/{feature.id}/effects")).json()
        assert static_items(after, "ability")[0]["amount"] == 1

    async def test_patch_to_an_unknown_skill_returns_422(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Retarget")
        skill = await create_skill(name="Arcana", ability="INT")
        created = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]
        )
        row_id = static_items(created.json(), "skill")[0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/effects/skill/{row_id}", json={"skill_id": 999999}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_row_of_another_feature_or_type_returns_404(self, client, gm_token, create_feature):
        owner = await create_feature(name="Owner")
        other = await create_feature(name="Other")
        created = await add_effects(
            client, gm_token, owner.id, [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]
        )
        row_id = static_items(created.json(), "armor")[0]["id"]

        foreign = await client.patch(
            f"/features/{other.id}/effects/armor/{row_id}", json={"armor_type": "HEAVY"}, headers=auth(gm_token)
        )
        wrong_type = await client.patch(
            f"/features/{owner.id}/effects/weapon/{row_id}", json={"weapon_category": "MARTIAL"}, headers=auth(gm_token)
        )

        assert foreign.status_code == 404
        assert wrong_type.status_code == 404

    async def test_unknown_effect_type_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Bad Type")

        response = await client.patch(f"/features/{feature.id}/effects/bogus/1", json={}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")

        response = await client.patch(f"/features/{feature.id}/effects/armor/1", json={}, headers=auth(player_token))

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestRemoveFixedEffect:
    async def test_removes_only_the_given_row(self, client, gm_token, create_feature):
        feature = await create_feature(name="Trim")
        created = await add_effects(
            client,
            gm_token,
            feature.id,
            [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}, {"armor_type": "HEAVY"}]}],
        )
        light = next(i for i in static_items(created.json(), "armor") if i["armor_type"] == "LIGHT")

        response = await client.delete(f"/features/{feature.id}/effects/armor/{light['id']}", headers=auth(gm_token))

        assert response.status_code == 200, response.text
        assert [i["armor_type"] for i in static_items(response.json(), "armor")] == ["HEAVY"]

    async def test_removing_the_last_effect_drops_the_group_and_the_flag(self, client, gm_token, create_feature):
        feature = await create_feature(name="Last One")
        created = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "saving_throw", "items": [{"ability": "WIS"}]}]
        )
        row_id = static_items(created.json(), "saving_throw")[0]["id"]

        response = await client.delete(f"/features/{feature.id}/effects/saving_throw/{row_id}", headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["static_groups"] == []
        assert (await client.get(f"/features/{feature.id}")).json()["has_static_effects"] is False

    async def test_missing_or_foreign_row_returns_404(self, client, gm_token, create_feature):
        owner = await create_feature(name="Owner")
        other = await create_feature(name="Other")
        created = await add_effects(
            client, gm_token, owner.id, [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]
        )
        row_id = static_items(created.json(), "armor")[0]["id"]

        foreign = await client.delete(f"/features/{other.id}/effects/armor/{row_id}", headers=auth(gm_token))
        missing = await client.delete(f"/features/{owner.id}/effects/armor/999999", headers=auth(gm_token))

        assert foreign.status_code == 404
        assert missing.status_code == 404
        assert len(static_items((await client.get(f"/features/{owner.id}/effects")).json(), "armor")) == 1

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")

        response = await client.delete(f"/features/{feature.id}/effects/armor/1", headers=auth(player_token))

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroups:
    async def test_creates_a_group_with_options_and_effects(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")

        response = await add_group(
            client,
            gm_token,
            feature.id,
            {
                "pick_count": 1,
                "choice_type": "ABILITY_SCORE",
                "options": [
                    {"effects": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]},
                    {
                        "sort_order": 1,
                        "effects": [{"effect_type": "ability", "items": [{"ability": "DEX", "amount": 1}]}],
                    },
                ],
            },
        )

        assert response.status_code == 201, response.text
        groups = response.json()
        assert len(groups) == 1
        assert groups[0]["choice_type"] == "ABILITY_SCORE"
        assert [effect_items(o["effects"], "ability")[0]["ability"] for o in groups[0]["options"]] == ["STR", "DEX"]
        assert (await client.get(f"/features/{feature.id}/choice-groups")).json() == groups
        assert (await client.get(f"/features/{feature.id}")).json()["has_choices"] is True

    async def test_creates_an_empty_group(self, client, gm_token, create_feature):
        feature = await create_feature(name="Empty Group")

        response = await add_group(client, gm_token, feature.id, {"choice_type": "SKILL"})

        assert response.status_code == 201
        assert response.json()[0]["options"] == []

    async def test_second_ability_score_group_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Two Asi")
        first = await add_group(client, gm_token, feature.id, {"choice_type": "ABILITY_SCORE"})
        assert first.status_code == 201

        second = await add_group(client, gm_token, feature.id, {"choice_type": "ABILITY_SCORE"})

        assert second.status_code == 422
        assert len((await client.get(f"/features/{feature.id}/choice-groups")).json()) == 1

    async def test_second_group_is_added_next_to_the_first(self, client, gm_token, create_feature):
        feature = await create_feature(name="Two Groups")

        await add_group(client, gm_token, feature.id, {"choice_type": "SKILL"})
        response = await add_group(client, gm_token, feature.id, {"choice_type": "WEAPON", "sort_order": 1})

        assert [g["choice_type"] for g in response.json()] == ["SKILL", "WEAPON"]

    @pytest.mark.parametrize(
        "payload",
        [
            {"id": 1, "choice_type": "SKILL"},
            {"choice_type": "SKILL", "options": [{"id": 1}]},
            {
                "choice_type": "SKILL",
                "options": [{"effects": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]}],
            },
            {"choice_type": "SKILL", "options": [{"effects": [{"effect_type": "skill", "items": [{}]}]}]},
            {"choice_type": "SKILL", "options": [skill_option(999999)]},
            {"choice_type": "SKILL", "pick_count": 0},
        ],
        ids=["group-id", "option-id", "wrong-effect-type", "open-skill", "unknown-skill", "pick-count"],
    )
    async def test_invalid_group_returns_422(self, client, gm_token, create_feature, payload):
        feature = await create_feature(name="Invalid Group")

        response = await add_group(client, gm_token, feature.id, payload)

        assert response.status_code == 422
        assert (await client.get(f"/features/{feature.id}/choice-groups")).json() == []

    async def test_patch_changes_pick_count_and_sort_order(self, client, gm_token, create_feature):
        feature = await create_feature(name="Tune")
        group_id = (await add_group(client, gm_token, feature.id, {"choice_type": "SKILL"})).json()[0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}",
            json={"pick_count": 3, "sort_order": 2},
            headers=auth(gm_token),
        )

        assert response.status_code == 200, response.text
        assert (response.json()[0]["pick_count"], response.json()[0]["sort_order"]) == (3, 2)

    async def test_patch_with_a_single_field_keeps_the_other(self, client, gm_token, create_feature):
        feature = await create_feature(name="Partial")
        group_id = (await add_group(client, gm_token, feature.id, {"choice_type": "SKILL", "pick_count": 2})).json()[0][
            "id"
        ]

        response = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}", json={"sort_order": 4}, headers=auth(gm_token)
        )

        assert (response.json()[0]["pick_count"], response.json()[0]["sort_order"]) == (2, 4)

    @pytest.mark.parametrize(
        "changes",
        [{"pick_count": None}, {"pick_count": 51}, {"choice_type": "ARMOR"}],
        ids=["null", "too-big", "choice-type-is-immutable"],
    )
    async def test_invalid_patch_returns_422(self, client, gm_token, create_feature, changes):
        feature = await create_feature(name="Bad Patch")
        group_id = (await add_group(client, gm_token, feature.id, {"choice_type": "SKILL"})).json()[0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}", json=changes, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_group_of_another_feature_returns_404(self, client, gm_token, create_feature):
        owner = await create_feature(name="Owner")
        other = await create_feature(name="Other")
        group_id = (await add_group(client, gm_token, owner.id, {"choice_type": "SKILL"})).json()[0]["id"]

        patch = await client.patch(
            f"/features/{other.id}/choice-groups/{group_id}", json={"pick_count": 2}, headers=auth(gm_token)
        )
        delete = await client.delete(f"/features/{other.id}/choice-groups/{group_id}", headers=auth(gm_token))

        assert patch.status_code == 404
        assert delete.status_code == 404

    async def test_delete_removes_the_group_with_its_options(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Drop Group")
        skill = await create_skill(name="Stealth", ability="DEX")
        group_id = (
            await add_group(client, gm_token, feature.id, {"choice_type": "SKILL", "options": [skill_option(skill.id)]})
        ).json()[0]["id"]

        response = await client.delete(f"/features/{feature.id}/choice-groups/{group_id}", headers=auth(gm_token))

        assert response.status_code == 200, response.text
        assert response.json() == []
        assert (await client.get(f"/features/{feature.id}")).json()["has_choices"] is False

    async def test_delete_clears_the_characters_stored_pick(
        self, client, db_session, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature = await create_feature(name="Picked", source_type="CLASS", level=None)
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        skill = await create_skill(name="Stealth", ability="DEX")
        group = (
            await add_group(client, gm_token, feature.id, {"choice_type": "SKILL", "options": [skill_option(skill.id)]})
        ).json()[0]
        grant = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={
                "feature_id": feature.id,
                "choices": [{"choice_group_id": group["id"], "choice_option_id": group["options"][0]["id"]}],
            },
            headers=auth(gm_token),
        )
        assert grant.status_code == 201, grant.text
        picks = select(func.count()).select_from(CharacterFeatureChoice)
        assert await db_session.scalar(picks) == 1

        delete = await client.delete(f"/features/{feature.id}/choice-groups/{group['id']}", headers=auth(gm_token))

        assert delete.status_code == 200, delete.text
        assert await db_session.scalar(picks) == 0

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")

        post = await add_group(client, player_token, feature.id, {"choice_type": "SKILL"})
        patch = await client.patch(f"/features/{feature.id}/choice-groups/1", json={}, headers=auth(player_token))
        delete = await client.delete(f"/features/{feature.id}/choice-groups/1", headers=auth(player_token))

        assert (post.status_code, patch.status_code, delete.status_code) == (403, 403, 403)


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceOptions:
    async def group(self, client, gm_token, feature_id, choice_type="SKILL"):
        """The id of a freshly added group — the POST answers with the feature's whole group list."""

        created = await add_group(client, gm_token, feature_id, {"choice_type": choice_type})
        return max(group["id"] for group in created.json())

    async def test_adds_an_option_with_its_bundle(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Skilled")
        skill = await create_skill(name="Stealth", ability="DEX")
        group_id = await self.group(client, gm_token, feature.id)

        response = await client.post(
            f"/features/{feature.id}/choice-groups/{group_id}/options",
            json={"sort_order": 1, **skill_option(skill.id)},
            headers=auth(gm_token),
        )

        assert response.status_code == 201, response.text
        option = response.json()[0]["options"][0]
        assert option["sort_order"] == 1
        assert effect_items(option["effects"], "skill")[0]["skill_id"] == skill.id

    @pytest.mark.parametrize(
        "payload",
        [
            {"id": 1},
            {"effects": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
            {"effects": [{"effect_type": "skill", "items": [{}]}]},
            {"effects": [{"effect_type": "skill", "items": [{"skill_id": 999999}]}]},
        ],
        ids=["id", "wrong-effect-type", "open-skill", "unknown-skill"],
    )
    async def test_invalid_option_returns_422(self, client, gm_token, create_feature, payload):
        feature = await create_feature(name="Bad Option")
        group_id = await self.group(client, gm_token, feature.id)

        response = await client.post(
            f"/features/{feature.id}/choice-groups/{group_id}/options", json=payload, headers=auth(gm_token)
        )

        assert response.status_code == 422
        assert (await client.get(f"/features/{feature.id}/choice-groups")).json()[0]["options"] == []

    async def test_option_in_a_missing_group_returns_404(self, client, gm_token, create_feature):
        feature = await create_feature(name="No Group")

        response = await client.post(
            f"/features/{feature.id}/choice-groups/999999/options", json={}, headers=auth(gm_token)
        )

        assert response.status_code == 404

    async def test_patch_changes_sort_order(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Reorder")
        skill = await create_skill(name="Stealth", ability="DEX")
        group_id = await self.group(client, gm_token, feature.id)
        created = await client.post(
            f"/features/{feature.id}/choice-groups/{group_id}/options",
            json=skill_option(skill.id),
            headers=auth(gm_token),
        )
        option_id = created.json()[0]["options"][0]["id"]

        response = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}/options/{option_id}",
            json={"sort_order": 7},
            headers=auth(gm_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()[0]["options"][0]["sort_order"] == 7

    async def test_patch_rejects_a_missing_or_unknown_field(self, client, gm_token, create_feature):
        feature = await create_feature(name="Strict Option")
        group_id = await self.group(client, gm_token, feature.id)
        created = await client.post(
            f"/features/{feature.id}/choice-groups/{group_id}/options", json={}, headers=auth(gm_token)
        )
        url = f"/features/{feature.id}/choice-groups/{group_id}/options/{created.json()[0]['options'][0]['id']}"

        assert (await client.patch(url, json={}, headers=auth(gm_token))).status_code == 422
        assert (await client.patch(url, json={"effects": []}, headers=auth(gm_token))).status_code == 422

    async def test_option_of_another_group_returns_404(self, client, gm_token, create_feature):
        feature = await create_feature(name="Two Groups")
        group_a = await self.group(client, gm_token, feature.id)
        group_b = await self.group(client, gm_token, feature.id)
        created = await client.post(
            f"/features/{feature.id}/choice-groups/{group_a}/options", json={}, headers=auth(gm_token)
        )
        option_id = created.json()[0]["options"][0]["id"]

        patch = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_b}/options/{option_id}",
            json={"sort_order": 1},
            headers=auth(gm_token),
        )
        delete = await client.delete(
            f"/features/{feature.id}/choice-groups/{group_b}/options/{option_id}", headers=auth(gm_token)
        )

        assert patch.status_code == 404
        assert delete.status_code == 404

    async def test_delete_removes_the_option_and_reverts_picks(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature = await create_feature(name="Pick Then Drop", source_type="CLASS", level=None)
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Rogue")).id)
        stealth = await create_skill(name="Stealth", ability="DEX")
        arcana = await create_skill(name="Arcana", ability="INT")
        group = (
            await add_group(
                client,
                gm_token,
                feature.id,
                {"choice_type": "SKILL", "options": [skill_option(stealth.id), skill_option(arcana.id)]},
            )
        ).json()[0]
        picked, other = group["options"][0]["id"], group["options"][1]["id"]
        grant = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id, "choices": [{"choice_group_id": group["id"], "choice_option_id": picked}]},
            headers=auth(gm_token),
        )
        assert grant.status_code == 201, grant.text
        choices_url = f"/characters/{character.id}/features/{grant.json()['id']}/choices"
        assert (await client.get(choices_url, headers=auth(gm_token))).json()["groups"] == []

        response = await client.delete(
            f"/features/{feature.id}/choice-groups/{group['id']}/options/{picked}", headers=auth(gm_token)
        )

        assert response.status_code == 200, response.text
        assert [o["id"] for o in response.json()[0]["options"]] == [other]
        assert len((await client.get(choices_url, headers=auth(gm_token))).json()["groups"]) == 1

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")
        base = f"/features/{feature.id}/choice-groups/1/options"

        post = await client.post(base, json={}, headers=auth(player_token))
        patch = await client.patch(f"{base}/1", json={"sort_order": 1}, headers=auth(player_token))
        delete = await client.delete(f"{base}/1", headers=auth(player_token))

        assert (post.status_code, patch.status_code, delete.status_code) == (403, 403, 403)


@pytest.mark.integration
@pytest.mark.asyncio
class TestOptionEffects:
    async def option(self, client, gm_token, feature_id, choice_type="WEAPON", effects=None):
        """Create a group with one option; returns the option's base url."""

        group = (
            await add_group(
                client,
                gm_token,
                feature_id,
                {"choice_type": choice_type, "options": [{"effects": effects or []}]},
            )
        ).json()[0]
        return f"/features/{feature_id}/choice-groups/{group['id']}/options/{group['options'][0]['id']}"

    async def test_add_patch_and_remove_an_effect(self, client, gm_token, create_feature):
        feature = await create_feature(name="Combat Style")
        url = await self.option(client, gm_token, feature.id)

        added = await client.post(
            f"{url}/effects",
            json={"static_groups": [{"effect_type": "weapon", "items": [{"weapon_category": "MARTIAL"}]}]},
            headers=auth(gm_token),
        )
        assert added.status_code == 201, added.text
        row = effect_items(added.json()[0]["options"][0]["effects"], "weapon")[0]
        assert row["weapon_category"] == "MARTIAL"

        patched = await client.patch(
            f"{url}/effects/weapon/{row['id']}", json={"weapon_category": "SIMPLE"}, headers=auth(gm_token)
        )
        assert patched.status_code == 200, patched.text
        assert effect_items(patched.json()[0]["options"][0]["effects"], "weapon") == [
            {"id": row["id"], "weapon_category": "SIMPLE", "item_id": None}
        ]

        removed = await client.delete(f"{url}/effects/weapon/{row['id']}", headers=auth(gm_token))
        assert removed.status_code == 200, removed.text
        assert removed.json()[0]["options"][0]["effects"] == []

    async def test_effect_type_must_match_the_group_choice_type(self, client, gm_token, create_feature):
        feature = await create_feature(name="Mismatch")
        url = await self.option(client, gm_token, feature.id, choice_type="WEAPON")

        response = await client.post(
            f"{url}/effects",
            json={"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
            headers=auth(gm_token),
        )

        assert response.status_code == 422

    async def test_open_skill_and_unknown_skill_return_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Skill Option")
        url = await self.option(client, gm_token, feature.id, choice_type="SKILL")

        for item in ({}, {"skill_id": 999999}, {"id": 3, "skill_id": 1}):
            response = await client.post(
                f"{url}/effects",
                json={"static_groups": [{"effect_type": "skill", "items": [item]}]},
                headers=auth(gm_token),
            )
            assert response.status_code == 422, item

    async def test_patch_that_breaks_validation_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Weapon Rule")
        url = await self.option(
            client, gm_token, feature.id, effects=[{"effect_type": "weapon", "items": [{"weapon_category": "MARTIAL"}]}]
        )
        row_id = effect_items(
            (await client.get(f"/features/{feature.id}/choice-groups")).json()[0]["options"][0]["effects"], "weapon"
        )[0]["id"]

        response = await client.patch(
            f"{url}/effects/weapon/{row_id}", json={"item_id": 999999}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_effect_of_a_feature_level_row_is_not_reachable_through_an_option(
        self, client, gm_token, create_feature
    ):
        feature = await create_feature(name="Mixed")
        fixed = await add_effects(
            client, gm_token, feature.id, [{"effect_type": "weapon", "items": [{"weapon_category": "SIMPLE"}]}]
        )
        fixed_id = static_items(fixed.json(), "weapon")[0]["id"]
        url = await self.option(client, gm_token, feature.id)

        patch = await client.patch(
            f"{url}/effects/weapon/{fixed_id}", json={"weapon_category": "MARTIAL"}, headers=auth(gm_token)
        )
        delete = await client.delete(f"{url}/effects/weapon/{fixed_id}", headers=auth(gm_token))

        assert patch.status_code == 404
        assert delete.status_code == 404
        assert static_items((await client.get(f"/features/{feature.id}/effects")).json(), "weapon")[0]["id"] == fixed_id

    async def test_player_is_forbidden(self, client, player_token, create_feature):
        feature = await create_feature(name="Players Keep Out")
        base = f"/features/{feature.id}/choice-groups/1/options/1/effects"

        post = await client.post(base, json={"static_groups": []}, headers=auth(player_token))
        patch = await client.patch(f"{base}/weapon/1", json={}, headers=auth(player_token))
        delete = await client.delete(f"{base}/weapon/1", headers=auth(player_token))

        assert (post.status_code, patch.status_code, delete.status_code) == (403, 403, 403)
