"""
Open ("any skill") picks and skill-effect modes end to end: an option without
``skill_id`` is picked with a named skill, and every skill pick is judged
against the character's other sources (no wasted proficiency, expertise only
on a skill the character is proficient in).
"""

import pytest
import pytest_asyncio

from tests.helpers import set_choice_groups, set_effects


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def skill_group(client, gm_token, feature_id, *, pick_count=1, items=({},)):
    """Give the feature one SKILL group with a single option carrying ``items`` (default: one open effect)."""

    response = await set_choice_groups(
        client,
        gm_token,
        feature_id,
        {
            "choice_groups": [
                {
                    "pick_count": pick_count,
                    "choice_type": "SKILL",
                    "options": [{"effects": [{"effect_type": "skill", "items": list(items)}]}],
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
                {"choice_group_id": group_id, "choice_option_id": option_id, "skill_id": skill_id}
                for group_id, option_id, skill_id in picks
            ]
        },
        headers=_auth(token),
    )


async def skills(client, token, character_id) -> dict[int, bool]:
    """``skill_id -> is_expertise`` of the character's resolved skill proficiencies."""

    response = await client.get(f"/characters/{character_id}/proficiencies", headers=_auth(token))
    assert response.status_code == 200, response.text
    return {entry["skill_id"]: entry["is_expertise"] for entry in response.json()["skills"]}


async def pending_option(client, token, character_id, grant_id) -> dict:
    response = await client.get(f"/characters/{character_id}/features/{grant_id}/choices", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()["groups"][0]["options"][0]


@pytest_asyncio.fixture
async def setup(gm, create_class, create_character, create_skill):
    """A character with no proficiencies and three skills in the catalog."""

    rogue = await create_class(name="Rogue")
    character = await create_character(owner_id=gm.id, class_id=rogue.id)
    stealth = await create_skill(name="Stealth", ability="DEX")
    arcana = await create_skill(name="Arcana", ability="INT")
    history = await create_skill(name="History", ability="INT")
    return character, stealth, arcana, history


async def proficient_in(client, gm_token, create_feature, character_id, skill_id, name="Training"):
    """Grant the character a feature whose fixed effect gives proficiency in ``skill_id``."""

    feature = await create_feature(name=name, source_type="OTHER", level=None)
    added = await set_effects(
        client, gm_token, feature.id, {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]}
    )
    assert added.status_code == 200, added.text
    await grant(client, gm_token, character_id, feature.id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenSkillPicks:
    async def test_any_two_skills_from_one_open_option(self, client, gm_token, create_feature, setup):
        character, stealth, arcana, history = setup
        feature = await create_feature(name="Skilled", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id, pick_count=2)
        grant_id = await grant(client, gm_token, character.id, feature.id)

        option = await pending_option(client, gm_token, character.id, grant_id)
        assert option["needs_skill"] is True
        assert option["allowed_skill_ids"] == sorted([stealth.id, arcana.id, history.id])
        assert option["available"] is True

        picks = [(group_id, option_id, stealth.id), (group_id, option_id, arcana.id)]
        response = await answer(client, gm_token, character.id, grant_id, picks)
        assert response.status_code == 200, response.text
        assert response.json()["groups"] == []

        assert await skills(client, gm_token, character.id) == {stealth.id: False, arcana.id: False}

        answered = await client.get(
            f"/characters/{character.id}/features/{grant_id}/choices/answered", headers=_auth(gm_token)
        )
        assert answered.status_code == 200, answered.text
        assert sorted(choice["picked_skill_id"] for choice in answered.json()["choices"]) == sorted(
            [stealth.id, arcana.id]
        )

    async def test_deleting_a_skill_picked_through_an_open_option_is_409(
        self, client, gm_token, founder_token, create_feature, setup
    ):
        character, stealth, _, _ = setup
        feature = await create_feature(name="Skilled", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id)
        grant_id = await grant(client, gm_token, character.id, feature.id)
        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, stealth.id)])
        assert response.status_code == 200, response.text

        deleted = await client.delete(f"/skills/{stealth.id}", headers=_auth(founder_token))

        assert deleted.status_code == 409

    async def test_open_option_without_a_skill_is_422(self, client, gm_token, create_feature, setup):
        character, *_ = setup
        feature = await create_feature(name="Any Skill", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id)
        grant_id = await grant(client, gm_token, character.id, feature.id)

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, None)])

        assert response.status_code == 422
        assert "skill_id" in response.json()["error"]["message"]

    async def test_unknown_skill_is_422(self, client, gm_token, create_feature, setup):
        character, *_ = setup
        feature = await create_feature(name="Any Skill", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id)
        grant_id = await grant(client, gm_token, character.id, feature.id)

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, 999_999)])

        assert response.status_code == 422

    async def test_proficiency_the_character_already_has_is_refused(self, client, gm_token, create_feature, setup):
        character, stealth, arcana, history = setup
        await proficient_in(client, gm_token, create_feature, character.id, stealth.id)
        feature = await create_feature(name="Any Skill", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id)
        grant_id = await grant(client, gm_token, character.id, feature.id)

        option = await pending_option(client, gm_token, character.id, grant_id)
        assert option["allowed_skill_ids"] == sorted([arcana.id, history.id])

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, stealth.id)])
        assert response.status_code == 422
        assert "already proficient" in response.json()["error"]["message"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestExpertisePicks:
    async def test_expertise_only_on_a_skill_the_character_is_proficient_in(
        self, client, gm_token, create_feature, setup
    ):
        character, stealth, arcana, _ = setup
        # the refused (422) answer rolls the shared session back and expires fixture rows: read the ids up front
        character_id, stealth_id, arcana_id = character.id, stealth.id, arcana.id
        await proficient_in(client, gm_token, create_feature, character_id, stealth_id)
        expertise = await create_feature(name="Expertise", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, expertise.id, items=({"mode": "EXPERTISE"},))
        grant_id = await grant(client, gm_token, character_id, expertise.id)

        option = await pending_option(client, gm_token, character_id, grant_id)
        assert option["allowed_skill_ids"] == [stealth_id]

        refused = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, arcana_id)])
        assert refused.status_code == 422
        assert "needs proficiency" in refused.json()["error"]["message"]

        accepted = await answer(client, gm_token, character_id, grant_id, [(group_id, option_id, stealth_id)])
        assert accepted.status_code == 200, accepted.text

        assert await skills(client, gm_token, character_id) == {stealth_id: True}

    async def test_concrete_expertise_option_without_proficiency_is_unavailable(
        self, client, gm_token, create_feature, setup
    ):
        character, _, arcana, _ = setup
        feature = await create_feature(name="Scholar", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(
            client, gm_token, feature.id, items=({"skill_id": arcana.id, "mode": "EXPERTISE"},)
        )
        grant_id = await grant(client, gm_token, character.id, feature.id)

        option = await pending_option(client, gm_token, character.id, grant_id)
        assert option["needs_skill"] is False
        assert option["available"] is False

        response = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, None)])
        assert response.status_code == 422

    async def test_expertise_whose_proficiency_is_lost_gives_nothing(self, client, gm_token, create_feature, setup):
        character, stealth, *_ = setup
        training = await create_feature(name="Training", source_type="OTHER", level=None)
        stealth_training = {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": stealth.id}]}]}
        await set_effects(client, gm_token, training.id, stealth_training)
        await grant(client, gm_token, character.id, training.id)
        expertise = await create_feature(name="Expertise", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, expertise.id, items=({"mode": "EXPERTISE"},))
        grant_id = await grant(client, gm_token, character.id, expertise.id)
        accepted = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, stealth.id)])
        assert accepted.status_code == 200, accepted.text

        removed = await client.delete(
            f"/characters/{character.id}/gm-panel/features", params={"feature_id": training.id}, headers=_auth(gm_token)
        )
        assert removed.status_code == 204, removed.text

        assert await skills(client, gm_token, character.id) == {}

    async def test_upgrade_turns_an_existing_proficiency_into_expertise(self, client, gm_token, create_feature, setup):
        character, stealth, arcana, _ = setup
        await proficient_in(client, gm_token, create_feature, character.id, stealth.id)
        feature = await create_feature(name="Keen Senses", source_type="OTHER", level=None)
        added = await set_effects(
            client,
            gm_token,
            feature.id,
            {
                "static_groups": [
                    {
                        "effect_type": "skill",
                        "items": [
                            {"skill_id": stealth.id, "mode": "UPGRADE"},
                            {"skill_id": arcana.id, "mode": "UPGRADE"},
                        ],
                    }
                ]
            },
        )
        assert added.status_code == 200, added.text
        await grant(client, gm_token, character.id, feature.id)

        assert await skills(client, gm_token, character.id) == {stealth.id: True, arcana.id: False}


@pytest.mark.integration
@pytest.mark.asyncio
class TestOptionReshape:
    async def test_making_a_picked_option_open_clears_its_picks(self, client, gm_token, create_feature, setup):
        character, stealth, *_ = setup
        feature = await create_feature(name="Pick", source_type="OTHER", level=None)
        group_id, option_id = await skill_group(client, gm_token, feature.id, items=({"skill_id": stealth.id},))
        grant_id = await grant(client, gm_token, character.id, feature.id)
        accepted = await answer(client, gm_token, character.id, grant_id, [(group_id, option_id, None)])
        assert accepted.status_code == 200, accepted.text

        tree = await client.get(f"/features/{feature.id}/choice-groups")
        effect_id = tree.json()[0]["options"][0]["effects"][0]["items"][0]["id"]
        reshaped = await client.patch(
            f"/features/{feature.id}/choice-groups/{group_id}/options/{option_id}/effects/skill/{effect_id}",
            json={"skill_id": None},
            headers=_auth(gm_token),
        )
        assert reshaped.status_code == 200, reshaped.text

        option = await pending_option(client, gm_token, character.id, grant_id)
        assert option["needs_skill"] is True
        assert await skills(client, gm_token, character.id) == {}
