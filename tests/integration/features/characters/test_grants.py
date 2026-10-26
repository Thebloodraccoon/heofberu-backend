"""Tests for character grant choice endpoints: GET/PATCH /characters/{id}/features/{cfid}/choices."""

import pytest

from tests.helpers import effect_items, set_choice_groups, set_effects


@pytest.mark.integration
@pytest.mark.asyncio
class TestPendingChoiceGroups:
    async def test_grant_with_no_choice_groups_returns_empty(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Extra Attack", source_type="CLASS", level=None)

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        response = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["character_feature_id"] == cf_id
        assert body["feature_id"] == feature.id
        assert body["groups"] == []

    async def test_grant_with_one_group_returns_pending_options(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Training", source_type="CLASS", level=None)

        # Add a choice group with two options, each granting a skill
        resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # GET pending choices — should list the one group with two options
        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choices_resp.status_code == 200
        body = choices_resp.json()
        assert body["character_feature_id"] == cf_id
        assert len(body["groups"]) == 1
        group = body["groups"][0]
        assert group["pick_count"] == 1
        assert len(group["options"]) == 2
        for opt in group["options"]:
            assert "id" in opt
            assert opt["needs_skill"] is False

        # Effects are NOT yet materialized — the grant is pending.
        char_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert char_resp.status_code == 200
        skill_ids = [s["skill_id"] for s in char_resp.json()["skills"]]
        assert skill.id not in skill_ids

    async def test_grant_not_belonging_to_character_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        char_a = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Char A")
        char_b = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Char B")
        feature = await create_feature(name="Shared", source_type="CLASS", level=None)

        grant_resp_a = await client.post(
            f"/characters/{char_a.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp_a.status_code == 201
        cf_id_a = grant_resp_a.json()["id"]

        # Try to read char_a's grant via char_b — should 404
        response = await client.get(
            f"/characters/{char_b.id}/features/{cf_id_a}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestPendingChoiceCount:
    async def test_count_is_zero_without_pending_choices(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Plain", source_type="CLASS", level=None)
        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text

        response = await client.get(
            f"/characters/{character.id}/grants/pending/count",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json() == {"count": 0}

    async def test_count_is_the_number_of_grants_with_unanswered_groups(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        grant_ids = []
        for name in ("First Training", "Second Training"):
            feature = await create_feature(name=name, source_type="CLASS", level=None)
            groups_resp = await set_choice_groups(
                client,
                gm_token,
                feature.id,
                {
                    "choice_groups": [
                        {
                            "pick_count": 1,
                            "choice_type": "SKILL",
                            "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}],
                        }
                    ]
                },
            )
            assert groups_resp.status_code == 200, groups_resp.text
            grant_resp = await client.post(
                f"/characters/{character.id}/gm-panel/features",
                json={"feature_id": feature.id},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert grant_resp.status_code == 201, grant_resp.text
            grant_ids.append((grant_resp.json()["id"], groups_resp.json()[0]))

        plain = await create_feature(name="Plain", source_type="CLASS", level=None)
        await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": plain.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        headers = {"Authorization": f"Bearer {gm_token}"}

        assert (await client.get(f"/characters/{character.id}/grants/pending/count", headers=headers)).json() == {
            "count": 2
        }

        first_cf_id, first_group = grant_ids[0]
        answer = await client.patch(
            f"/characters/{character.id}/features/{first_cf_id}/choices",
            json={
                "answers": [
                    {
                        "choice_group_id": first_group["id"],
                        "choice_option_id": first_group["options"][0]["id"],
                    }
                ]
            },
            headers=headers,
        )
        assert answer.status_code == 200, answer.text

        response = await client.get(f"/characters/{character.id}/grants/pending/count", headers=headers)
        assert response.json() == {"count": 1}

    async def test_count_for_an_unknown_character_is_404(self, client, gm_token):
        response = await client.get(
            "/characters/999999/grants/pending/count", headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnswerChoices:
    async def test_patch_valid_option_materializes_skill(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill, db_session
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Pick", source_type="CLASS", level=None)

        # Set up a choice group with two skill options
        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        # Grant the feature
        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # PATCH answer the group
        answer_resp = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answer_resp.status_code == 200
        assert answer_resp.json()["groups"] == []

        # Skill should be materialized
        char_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert char_resp.status_code == 200
        skill_ids = [s["skill_id"] for s in char_resp.json()["skills"]]
        assert skill.id in skill_ids

    async def test_patch_wrong_option_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Pick", source_type="CLASS", level=None)

        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # Try a bogus option_id not in the group
        answer_resp = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": 999999}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answer_resp.status_code == 404

    async def test_patch_wrong_count_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill1 = await create_skill(name="Athletics", ability="STR")
        feature = await create_feature(name="Double Pick", source_type="CLASS", level=None)

        # Group requires pick_count=2
        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 2,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill1.id}]}]},
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill1.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # Send only 1 answer for a pick_count=2 group
        answer_resp = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answer_resp.status_code == 422

    async def test_re_answer_replaces_old_choice(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill, db_session
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill_a = await create_skill(name="Stealth", ability="DEX")
        skill_b = await create_skill(name="Perception", ability="WIS")
        feature = await create_feature(name="Skill Switch", source_type="CLASS", level=None)

        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill_a.id}]}]},
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill_b.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        opt_a_id = cg_resp.json()[0]["options"][0]["id"]
        opt_b_id = cg_resp.json()[0]["options"][1]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # Answer with option A
        ans1 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": opt_a_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans1.status_code == 200
        char_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids_after_a = [s["skill_id"] for s in char_resp.json()["skills"]]
        assert skill_a.id in skill_ids_after_a

        # Re-answer with option B
        ans2 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": opt_b_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans2.status_code == 200

        # skill_a should be gone, skill_b present
        char_resp2 = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids_after_b = [s["skill_id"] for s in char_resp2.json()["skills"]]
        assert skill_a.id not in skill_ids_after_b
        assert skill_b.id in skill_ids_after_b

    async def test_open_skill_without_skill_id_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Any Skill Pick", source_type="CLASS", level=None)

        # an open ("any skill") option: a skill effect without skill_id
        groups = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{}]}]}],
                    }
                ]
            },
        )
        assert groups.status_code == 200, groups.text
        group_id = groups.json()[0]["id"]
        option_id = groups.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # GET should show needs_skill=True for this option
        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choices_resp.status_code == 200
        assert choices_resp.json()["groups"][0]["options"][0]["needs_skill"] is True

        # PATCH without skill_id → 422 SkillPickRequiredError
        ans_no_skill = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans_no_skill.status_code == 422

    async def test_open_skill_with_skill_id_grants_that_skill(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Arcana", ability="INT")
        feature = await create_feature(name="Any Skill Resolve", source_type="CLASS", level=None)

        groups = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{}]}]}],
                    }
                ]
            },
        )
        assert groups.status_code == 200, groups.text
        group_id = groups.json()[0]["id"]
        option_id = groups.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "skill_id": skill.id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 200, ans.text

        proficiencies = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert [entry["skill_id"] for entry in proficiencies.json()["skills"]] == [skill.id]

    async def test_option_from_different_group_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Bard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Persuasion", ability="CHA")
        feature = await create_feature(name="Multi Group", source_type="CLASS", level=None)

        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    },
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_a_id = cg_resp.json()[0]["id"]
        opt_b1_id = cg_resp.json()[1]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        # Send group_a's id with group_b's option → should 404
        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_a_id, "choice_option_id": opt_b1_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 404

    async def test_patch_grant_not_belonging_to_character_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Fighter")
        char_a = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Char A")
        char_b = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Char B")
        skill = await create_skill(name="Athletics", ability="STR")
        feature = await create_feature(name="Switcheroo", source_type="CLASS", level=None)

        cg_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp_a = await client.post(
            f"/characters/{char_a.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp_a.status_code == 201
        cf_id_a = grant_resp_a.json()["id"]

        # Try to answer char_a's grant via char_b → 404
        ans = await client.patch(
            f"/characters/{char_b.id}/features/{cf_id_a}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenSpellResolution:
    """An open ("any spell") option: an extra spell the player picks, narrowed by the option's filter."""

    async def _grant_open_spell_feature(self, client, gm, gm_token, create_class, create_character, create_feature):
        """A Wizard with a granted feature whose one SPELL group offers "any 1st-level evocation spell"."""

        feature_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Spell Pick", source_type="CLASS", level=None)

        groups_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "choice_type": "SPELL",
                        "pick_count": 1,
                        "options": [
                            {
                                "effects": [
                                    {
                                        "effect_type": "spell",
                                        "items": [{"max_level": "LEVEL_1", "schools": ["EVOCATION"]}],
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )
        assert groups_resp.status_code == 200, groups_resp.text
        group = groups_resp.json()[0]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        return character, grant_resp.json()["id"], group["id"], group["options"][0]["id"]

    async def test_pending_open_option_lists_only_the_spells_its_filter_allows(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        magic_missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")
        await create_spell(name="Shield", school="ABJURATION", level="LEVEL_1")
        character, cf_id, _, _ = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )

        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choices_resp.status_code == 200
        option = choices_resp.json()["groups"][0]["options"][0]
        assert option["needs_spell"] is True
        assert option["needs_skill"] is False
        assert option["available"] is True
        assert [spell["id"] for spell in option["allowed_spells"]] == [magic_missile.id]
        assert option["allowed_spells"][0]["name"] == "Magic Missile"

    async def test_picking_an_open_option_gives_the_named_spell(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        magic_missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={
                "answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "spell_id": magic_missile.id}]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 200, ans.text
        assert ans.json()["groups"] == []

        spells_resp = await client.get(
            f"/characters/{character.id}/spells",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert [spell["id"] for spell in spells_resp.json()["feature_spells"]] == [magic_missile.id]

        answered = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices/answered",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answered.json()["choices"][0]["picked_spell_id"] == magic_missile.id

    async def test_include_answered_returns_an_answered_group_judged_without_its_own_pick(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        magic_missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        burning_hands = await create_spell(name="Burning Hands", school="EVOCATION", level="LEVEL_1")
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )
        headers = {"Authorization": f"Bearer {gm_token}"}
        url = f"/characters/{character.id}/features/{cf_id}/choices"
        answer = {"choice_group_id": group_id, "choice_option_id": option_id}

        first = await client.patch(url, json={"answers": [{**answer, "spell_id": magic_missile.id}]}, headers=headers)
        assert first.status_code == 200, first.text

        assert (await client.get(url, headers=headers)).json()["groups"] == []
        response = await client.get(url, params={"include_answered": True}, headers=headers)

        assert response.status_code == 200
        (group,) = response.json()["groups"]
        assert group["id"] == group_id
        (option,) = group["options"]
        assert option["available"] is True
        # the grant's own pick in the group doesn't count as a spell the character already has
        assert {spell["id"] for spell in option["allowed_spells"]} == {magic_missile.id, burning_hands.id}

        again = await client.patch(url, json={"answers": [{**answer, "spell_id": burning_hands.id}]}, headers=headers)
        assert again.status_code == 200, again.text
        spells = (await client.get(f"/characters/{character.id}/spells", headers=headers)).json()
        assert [spell["id"] for spell in spells["feature_spells"]] == [burning_hands.id]

    async def test_deleting_a_spell_picked_through_an_open_option_is_409(
        self, client, gm, gm_token, founder_token, create_class, create_character, create_feature, create_spell
    ):
        magic_missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        # the 409 rolls the shared session back and expires fixture rows: read the ids up front
        spell_id = magic_missile.id
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )
        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "spell_id": spell_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 200, ans.text

        response = await client.delete(f"/spells/{spell_id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/spells/{spell_id}")).status_code == 200

    async def test_open_option_summary_names_the_classes_of_its_filter(
        self, client, gm_token, create_class, create_feature
    ):
        bard = await create_class(name="Bard")
        cleric = await create_class(name="Cleric")
        feature = await create_feature(name="Any Caster Spell", source_type="CLASS", level=None)
        groups_resp = await set_choice_groups(
            client,
            gm_token,
            feature.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SPELL",
                        "options": [
                            {"effects": [{"effect_type": "spell", "items": [{"class_ids": [cleric.id, bard.id]}]}]}
                        ],
                    }
                ]
            },
        )
        assert groups_resp.status_code == 200, groups_resp.text

        groups = (await client.get(f"/features/{feature.id}/choice-groups")).json()

        (spell_item,) = effect_items(groups[0]["options"][0]["effects"], "spell")
        assert spell_item["summary"] == ["из списка: Bard, Cleric"]
        assert spell_item["class_ids"] == [cleric.id, bard.id]

    async def test_a_spell_outside_the_filter_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        fireball = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "spell_id": fireball.id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 422
        assert "above the option's range" in ans.json()["error"]["message"]

    async def test_open_spell_without_spell_id_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 422
        assert "name the spell" in ans.json()["error"]["message"]

    async def test_a_spell_the_character_already_has_is_not_offered_nor_pickable(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        magic_missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        character, cf_id, group_id, option_id = await self._grant_open_spell_feature(
            client, gm, gm_token, create_class, create_character, create_feature
        )
        granted = await client.post(
            f"/characters/{character.id}/gm-panel/spells",
            json={"spell_id": magic_missile.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert granted.status_code == 201, granted.text

        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        option = choices_resp.json()["groups"][0]["options"][0]
        assert option["allowed_spells"] == []
        assert option["available"] is False

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={
                "answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "spell_id": magic_missile.id}]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 422
        assert "already has it" in ans.json()["error"]["message"]

    async def test_fixed_spell_effect_materializes_granted_spell(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        feature_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Bonus Cantrip", source_type="CLASS", level=None)

        cantrip = await create_spell(name="Prestidigitation", school="TRANSMUTATION", level="CANTRIP")

        fx_resp = await set_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "spell", "items": [{"spell_id": cantrip.id}]}]},
        )
        assert fx_resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choices_resp.json()["groups"] == []

        spells_resp = await client.get(
            f"/characters/{character.id}/spells",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        granted = spells_resp.json()["feature_spells"]
        assert len(granted) == 1
        assert granted[0]["id"] == cantrip.id
        assert granted[0]["name"] == "Prestidigitation"


@pytest.mark.integration
@pytest.mark.asyncio
class TestConcreteToolOptions:
    async def _setup(self, client, gm, gm_token, create_class, create_character, create_feature, create_item):
        """A character proficient with the lute through one grant, and a second grant choosing lute or flute."""

        auth = {"Authorization": f"Bearer {gm_token}"}
        lute = await create_item(name="Lute", kind="TOOL", tool_category="MUSICAL_INSTRUMENT")
        flute = await create_item(name="Flute", kind="TOOL", tool_category="MUSICAL_INSTRUMENT")
        character = await create_character(owner_id=gm.id, class_id=(await create_class(name="Bard")).id)

        fixed = await create_feature(name="Minstrel", source_type="CLASS", level=None)
        resp = await set_effects(
            client, gm_token, fixed.id, {"static_groups": [{"effect_type": "tool", "items": [{"item_id": lute.id}]}]}
        )
        assert resp.status_code in (200, 201), resp.text
        grant = await client.post(
            f"/characters/{character.id}/gm-panel/features", json={"feature_id": fixed.id}, headers=auth
        )
        assert grant.status_code == 201, grant.text

        choice = await create_feature(name="Instrument Training", source_type="CLASS", level=None)
        groups = await set_choice_groups(
            client,
            gm_token,
            choice.id,
            {
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "TOOL",
                        "options": [
                            {"effects": [{"effect_type": "tool", "items": [{"item_id": lute.id}]}]},
                            {"effects": [{"effect_type": "tool", "items": [{"item_id": flute.id}]}]},
                        ],
                    }
                ]
            },
        )
        assert groups.status_code == 200, groups.text
        group = groups.json()[0]
        grant = await client.post(
            f"/characters/{character.id}/gm-panel/features", json={"feature_id": choice.id}, headers=auth
        )
        assert grant.status_code == 201, grant.text
        return character.id, grant.json()["id"], group["id"], [option["id"] for option in group["options"]], auth

    async def test_an_owned_concrete_tool_is_unavailable_and_refused(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_item
    ):
        character_id, cf_id, group_id, (lute_option, flute_option), auth = await self._setup(
            client, gm, gm_token, create_class, create_character, create_feature, create_item
        )

        pending = await client.get(f"/characters/{character_id}/features/{cf_id}/choices", headers=auth)
        assert pending.status_code == 200
        available = {option["id"]: option["available"] for option in pending.json()["groups"][0]["options"]}
        assert available == {lute_option: False, flute_option: True}

        refused = await client.patch(
            f"/characters/{character_id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": lute_option}]},
            headers=auth,
        )
        assert refused.status_code == 422, refused.text

        taken = await client.patch(
            f"/characters/{character_id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": flute_option}]},
            headers=auth,
        )
        assert taken.status_code == 200, taken.text
