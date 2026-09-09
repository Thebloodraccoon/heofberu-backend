"""Tests for character grant choice endpoints: GET/PATCH /characters/{id}/features/{cfid}/choices."""

import pytest


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
        assert grant_resp.status_code == 201
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
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Training", source_type="CLASS", level=None)

        # Add a choice group with two options, each granting a skill
        resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Choose a skill",
                        "options": [
                            {"label": "Stealth", "skill_effects": [{"skill_id": skill.id}]},
                            {"label": "Perception", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
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
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert char_resp.status_code == 200
        skill_ids = [s["skill_id"] for s in char_resp.json()["skill_proficiencies"]]
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
class TestAnswerChoices:
    async def test_patch_valid_option_materializes_skill(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill, db_session
    ):
        from app.models.character_association_models import CharacterSkillProficiency

        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Pick", source_type="CLASS", level=None)

        # Set up a choice group with two skill options
        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Skill",
                        "options": [
                            {"label": "Stealth", "skill_effects": [{"skill_id": skill.id}]},
                            {"label": "Perception", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
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
        assert grant_resp.status_code == 201
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
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert char_resp.status_code == 200
        skill_ids = [s["skill_id"] for s in char_resp.json()["skill_proficiencies"]]
        assert skill.id in skill_ids

    async def test_patch_wrong_option_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Pick", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Skill",
                        "options": [
                            {"label": "Stealth", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
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
        skill1 = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        feature = await create_feature(name="Double Pick", source_type="CLASS", level=None)

        # Group requires pick_count=2
        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 2,
                        "label": "Two Skills",
                        "options": [
                            {"label": "Athletics", "skill_effects": [{"skill_id": skill1.id}]},
                            {"label": "Acrobatics", "skill_effects": [{"skill_id": skill1.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
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
        from app.models.character_association_models import CharacterSkillProficiency

        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill_a = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        skill_b = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        feature = await create_feature(name="Skill Switch", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Skill",
                        "options": [
                            {"label": "Stealth", "skill_effects": [{"skill_id": skill_a.id}]},
                            {"label": "Perception", "skill_effects": [{"skill_id": skill_b.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
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
        assert grant_resp.status_code == 201
        cf_id = grant_resp.json()["id"]

        # Answer with option A
        ans1 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": opt_a_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans1.status_code == 200
        char_resp = await client.get(
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids_after_a = [s["skill_id"] for s in char_resp.json()["skill_proficiencies"]]
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
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids_after_b = [s["skill_id"] for s in char_resp2.json()["skill_proficiencies"]]
        assert skill_a.id not in skill_ids_after_b
        assert skill_b.id in skill_ids_after_b

    async def test_open_skill_without_skill_id_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Any Skill Pick", source_type="CLASS", level=None)

        # Option with open ("any") skill effect (skill_id=null)
        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Any Skill",
                        "options": [
                            {"label": "Any Skill", "skill_effects": [{"skill_id": None}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
        cf_id = grant_resp.json()["id"]

        # GET should show needs_skill=True for this option
        choices_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choices_resp.status_code == 200
        assert choices_resp.json()["groups"][0]["options"][0]["needs_skill"] is True

        # PATCH without skill_id → 422 SkillResolutionsError
        ans_no_skill = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans_no_skill.status_code == 422

    async def test_open_skill_with_skill_id_materializes(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        feature = await create_feature(name="Any Skill Resolve", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Any Skill",
                        "options": [
                            {"label": "Any Skill", "skill_effects": [{"skill_id": None}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
        cf_id = grant_resp.json()["id"]

        # PATCH with skill_id → 200
        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={
                "answers": [
                    {"choice_group_id": group_id, "choice_option_id": option_id, "skill_id": skill.id}
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 200
        assert ans.json()["groups"] == []

        char_resp = await client.get(
            f"/characters/{character.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids = [s["skill_id"] for s in char_resp.json()["skill_proficiencies"]]
        assert skill.id in skill_ids

    async def test_option_from_different_group_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Bard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(key="PERSUASION", name="Persuasion", ability="CHA")
        feature = await create_feature(name="Multi Group", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Group A",
                        "options": [
                            {"label": "A1", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    },
                    {
                        "pick_count": 1,
                        "label": "Group B",
                        "options": [
                            {"label": "B1", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    },
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_a_id = cg_resp.json()[0]["id"]
        opt_b1_id = cg_resp.json()[1]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
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
        skill = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        feature = await create_feature(name="Switcheroo", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Skill",
                        "options": [
                            {"label": "Athletics", "skill_effects": [{"skill_id": skill.id}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
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
