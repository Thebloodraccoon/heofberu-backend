"""
Open ("any ability" / "any saving throw") picks end to end: an ability-score or
saving-throw option without ``ability`` is picked with a named ability, which
then shows up in the character's totals / saving-throw proficiencies.
"""

import pytest
import pytest_asyncio

from tests.helpers import set_choice_groups, set_effects


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def choice_group(client, gm_token, feature_id, choice_type, effect_type, items, *, pick_count=1):
    """Give the feature one group of ``choice_type`` with a single option carrying ``items``."""

    response = await set_choice_groups(
        client,
        gm_token,
        feature_id,
        {
            "choice_groups": [
                {
                    "pick_count": pick_count,
                    "choice_type": choice_type,
                    "options": [{"effects": [{"effect_type": effect_type, "items": list(items)}]}],
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    group = response.json()[0]
    return group["id"], group["options"][0]["id"]


async def grant(client, gm_token, character_id, feature_id) -> int:
    response = await client.post(
        f"/characters/{character_id}/gm-panel/features", json={"feature_id": feature_id}, headers=_auth(gm_token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def answer(client, token, character_id, grant_id, picks):
    return await client.patch(
        f"/characters/{character_id}/features/{grant_id}/choices",
        json={
            "answers": [
                {"choice_group_id": group_id, "choice_option_id": option_id, "ability": ability}
                for group_id, option_id, ability in picks
            ]
        },
        headers=_auth(token),
    )


async def total(client, token, character_id, ability) -> int:
    response = await client.get(f"/characters/{character_id}/stats", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()[ability]["total"]


async def saving_throws(client, token, character_id) -> set[str]:
    response = await client.get(f"/characters/{character_id}/proficiencies", headers=_auth(token))
    assert response.status_code == 200, response.text
    return {item["ability"] for item in response.json()["saving_throws"]}


async def pending_option(client, token, character_id, grant_id) -> dict:
    response = await client.get(f"/characters/{character_id}/features/{grant_id}/choices", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["groups"][0]["options"][0]


@pytest_asyncio.fixture
async def character(gm, create_class, create_character):
    fighter = await create_class(name="Fighter")
    return await create_character(owner_id=gm.id, class_id=fighter.id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenAbilityPicks:
    async def test_any_ability_plus_two_raises_the_named_ability(self, client, gm_token, create_feature, character):
        character_id = character.id
        feature = await create_feature(name="Boon", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"amount": 2}]
        )
        grant_id = await grant(client, gm_token, character_id, feature.id)
        before = await total(client, gm_token, character_id, "wisdom")

        option = await pending_option(client, gm_token, character_id, grant_id)
        assert option["needs_ability"] is True

        response = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, "WIS")])
        assert response.status_code == 200, response.text
        assert response.json()["groups"] == []

        assert await total(client, gm_token, character_id, "wisdom") == before + 2
        answered = await client.get(
            f"/characters/{character_id}/features/{grant_id}/choices/answered", headers=_auth(gm_token)
        )
        assert answered.status_code == 200, answered.text
        assert [choice["picked_ability"] for choice in answered.json()["choices"]] == ["WIS"]

    async def test_one_open_option_fills_two_picks_with_different_abilities(
        self, client, gm_token, create_feature, character
    ):
        character_id = character.id
        feature = await create_feature(name="Versatile", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"amount": 1}], pick_count=2
        )
        grant_id = await grant(client, gm_token, character_id, feature.id)
        strength = await total(client, gm_token, character_id, "strength")
        dexterity = await total(client, gm_token, character_id, "dexterity")

        same = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, "STR")] * 2)
        assert same.status_code == 409

        picks = [(group_id, option_id, "STR"), (group_id, option_id, "DEX")]
        response = await answer(client, gm_token, character_id, grant_id, picks)
        assert response.status_code == 200, response.text

        assert await total(client, gm_token, character_id, "strength") == strength + 1
        assert await total(client, gm_token, character_id, "dexterity") == dexterity + 1

    async def test_open_option_without_an_ability_is_422(self, client, gm_token, create_feature, character):
        feature = await create_feature(name="Boon", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"amount": 2}]
        )
        grant_id = await grant(client, gm_token, character.id, feature.id)

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, None)])

        assert response.status_code == 422
        assert "'ability'" in response.json()["error"]["message"]

    async def test_ability_on_a_concrete_option_is_422(self, client, gm_token, create_feature, character):
        feature = await create_feature(name="Strong", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"ability": "STR", "amount": 1}]
        )
        grant_id = await grant(client, gm_token, character.id, feature.id)

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, "DEX")])

        assert response.status_code == 422

    async def test_open_pick_may_not_repeat_the_options_own_ability(
        self, client, gm_token, create_feature, character
    ):
        feature = await create_feature(name="Half Feat", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client,
            gm_token,
            feature.id,
            "ABILITY_SCORE",
            "ability",
            [{"ability": "STR", "amount": 1}, {"amount": 1}],
        )
        grant_id = await grant(client, gm_token, character.id, feature.id)

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, "STR")])

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenSavingThrowPicks:
    async def test_any_saving_throw_gives_the_named_proficiency(self, client, gm_token, create_feature, character):
        character_id = character.id
        feature = await create_feature(name="Resilient", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(client, gm_token, feature.id, "SAVING_THROW", "saving_throw", [{}])
        grant_id = await grant(client, gm_token, character_id, feature.id)
        before = await saving_throws(client, gm_token, character_id)

        option = await pending_option(client, gm_token, character_id, grant_id)
        assert option["needs_ability"] is True

        response = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, "CHA")])
        assert response.status_code == 200, response.text

        assert await saving_throws(client, gm_token, character_id) == before | {"CHA"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenAbilityAuthoring:
    async def test_fixed_effect_without_an_ability_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Broken", source_type="OTHER", level=None)

        for effect_type, item in (("ability", {"amount": 1}), ("saving_throw", {})):
            response = await set_effects(
                client, gm_token, feature.id, {"static_groups": [{"effect_type": effect_type, "items": [item]}]}
            )
            assert response.status_code == 422, effect_type

    async def test_summary_names_the_open_choice(self, client, gm_token, create_feature):
        feature = await create_feature(name="Boon", source_type="OTHER", level=None)
        await choice_group(client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"amount": 2}])

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200, response.text
        assert "Характеристики (выберите 1): +2 к любой" in response.json()["effects_summary"]

    async def test_making_a_picked_option_open_clears_its_picks(self, client, gm_token, create_feature, character):
        character_id = character.id
        feature = await create_feature(name="Strong", source_type="OTHER", level=None)
        group_id, option_id = await choice_group(
            client, gm_token, feature.id, "ABILITY_SCORE", "ability", [{"ability": "STR", "amount": 1}]
        )
        grant_id = await grant(client, gm_token, character_id, feature.id)
        accepted = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, None)])
        assert accepted.status_code == 200, accepted.text

        tree = await client.get(f"/features/{feature.id}/choice-groups")
        effect_id = tree.json()[0]["options"][0]["effects"][0]["items"][0]["id"]
        reshaped = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}/options/{option_id}/effects/ability/{effect_id}",
            json={"ability": None},
            headers=_auth(gm_token),
        )
        assert reshaped.status_code == 200, reshaped.text

        option = await pending_option(client, gm_token, character_id, grant_id)
        assert option["needs_ability"] is True
