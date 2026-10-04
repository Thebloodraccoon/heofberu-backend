"""
Coverage for the grant-effect paths test_grants.py never exercises:
saving-throw/armor/weapon proficiencies (fixed feature effects AND choice-
option effects), re-answer removing a stale proficiency, skill expertise
following the current pick, and feature-granted spells being computed
(``feature_spells``) rather than stored — see ``characters/grants/effects.py``.
"""

import pytest

from app.constants import ChoiceType
from app.models.features.feature_engine_models import FeatureChoiceGroup, FeatureChoiceOption, FeatureSpellGrantEffect


async def _seed_open_spell_choice_group(db_session, feature_id: int) -> tuple[int, int]:
    """
    Insert a SPELL choice group with one "any spell" (``spell_id=None``) option directly.

    Authoring an open pick through ``PUT /features/{id}/choice-groups`` is
    rejected by ``ChoiceGroupPayload.validate_no_open_picks`` — this
    simulates a pre-existing catalog row from before that validation was
    added, which the PATCH-time resolution guard still has to handle.
    """

    group = FeatureChoiceGroup(feature_id=feature_id, pick_count=1, choice_type=ChoiceType.SPELL)
    db_session.add(group)
    await db_session.flush()

    option = FeatureChoiceOption(group_id=group.id)
    db_session.add(option)
    await db_session.flush()

    db_session.add(FeatureSpellGrantEffect(choice_option_id=option.id, spell_id=None))
    await db_session.commit()

    return group.id, option.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestFixedEffectTypes:
    async def test_fixed_saving_throw_armor_weapon_effects_apply(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Martial Training", source_type="CLASS", level=None)

        fx_resp = await client.put(
            f"/features/{feature.id}/effects",
            json={
                "static_groups": [
                    {"effect_type": "saving_throw", "items": [{"ability": "STR"}]},
                    {"effect_type": "armor", "items": [{"armor_type": "MEDIUM"}]},
                    {"effect_type": "weapon", "items": [{"weapon_category": "MARTIAL"}]},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert fx_resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text

        prof_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert prof_resp.status_code == 200
        body = prof_resp.json()
        assert [s["ability"] for s in body["saving_throws"]] == ["STR"]
        assert [a["armor_type"] for a in body["armor"]] == ["MEDIUM"]
        assert [w["weapon_category"] for w in body["weapons"]] == ["MARTIAL"]

    async def test_fixed_weapon_item_effect_applies(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_item
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Signature Weapon", source_type="CLASS", level=None)
        longsword = await create_item(name="Longsword")

        fx_resp = await client.put(
            f"/features/{feature.id}/effects",
            json={"static_groups": [{"effect_type": "weapon", "items": [{"item_id": longsword.id}]}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert fx_resp.status_code == 200

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text

        prof_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        weapons = prof_resp.json()["weapons"]
        assert [w["item_id"] for w in weapons] == [longsword.id]


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceOptionEffectTypes:
    async def test_choice_option_saving_throw_armor_weapon_effects_apply(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        """Three separate single-type groups on one feature, answered together."""

        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Defensive Style", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SAVING_THROW",
                        "options": [{"effects": [{"effect_type": "saving_throw", "items": [{"ability": "CON"}]}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "ARMOR",
                        "options": [{"effects": [{"effect_type": "armor", "items": [{"armor_type": "SHIELD"}]}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "WEAPON",
                        "options": [{"effects": [{"effect_type": "weapon", "items": [{"weapon_category": "SIMPLE"}]}]}],
                    },
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        groups = cg_resp.json()

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        answer_resp = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={
                "answers": [
                    {"choice_group_id": group["id"], "choice_option_id": group["options"][0]["id"]} for group in groups
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answer_resp.status_code == 200

        prof_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        body = prof_resp.json()
        assert [s["ability"] for s in body["saving_throws"]] == ["CON"]
        assert [a["armor_type"] for a in body["armor"]] == ["SHIELD"]
        assert [w["weapon_category"] for w in body["weapons"]] == ["SIMPLE"]

    async def test_reanswer_removes_stale_weapon_proficiency_and_adds_new(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Combat Style", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "WEAPON",
                        "options": [
                            {"effects": [{"effect_type": "weapon", "items": [{"weapon_category": "MARTIAL"}]}]},
                            {"effects": [{"effect_type": "weapon", "items": [{"weapon_category": "SIMPLE"}]}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        martial_option_id = cg_resp.json()[0]["options"][0]["id"]
        simple_option_id = cg_resp.json()[0]["options"][1]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        ans1 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": martial_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans1.status_code == 200
        after_first = (
            await client.get(
                f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
            )
        ).json()
        assert [w["weapon_category"] for w in after_first["weapons"]] == ["MARTIAL"]

        ans2 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": simple_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans2.status_code == 200

        after_second = (
            await client.get(
                f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
            )
        ).json()
        assert [w["weapon_category"] for w in after_second["weapons"]] == ["SIMPLE"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestSkillExpertiseFollowsPick:
    async def test_reanswer_without_expertise_drops_it(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        """
        Effects are computed from the current pick, so re-answering with an
        option that doesn't grant expertise takes it away again.
        """

        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Focus", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [
                            {
                                "effects": [
                                    {
                                        "effect_type": "skill",
                                        "items": [{"skill_id": skill.id, "grants_expertise": False}],
                                    }
                                ]
                            },
                            {
                                "effects": [
                                    {
                                        "effect_type": "skill",
                                        "items": [{"skill_id": skill.id, "grants_expertise": True}],
                                    }
                                ]
                            },
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200
        group_id = cg_resp.json()[0]["id"]
        plain_option_id = cg_resp.json()[0]["options"][0]["id"]
        expertise_option_id = cg_resp.json()[0]["options"][1]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        # Answer with the expertise-granting option first.
        ans1 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": expertise_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans1.status_code == 200
        skills_after_expertise = (
            await client.get(
                f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
            )
        ).json()["skills"]
        row = next(s for s in skills_after_expertise if s["skill_id"] == skill.id)
        assert row["is_expertise"] is True

        # Re-answer with the plain (non-expertise) option — expertise goes away.
        ans2 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": plain_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans2.status_code == 200
        skills_after_plain = (
            await client.get(
                f"/characters/{character.id}/proficiencies", headers={"Authorization": f"Bearer {gm_token}"}
            )
        ).json()["skills"]
        row = next(s for s in skills_after_plain if s["skill_id"] == skill.id)
        assert row["is_expertise"] is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnswerChoicesAdditionalErrors:
    async def test_unknown_choice_group_returns_404(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Stealth", ability="DEX")
        feature = await create_feature(name="Skill Pick", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        # A group id that belongs to no group on this feature at all
        # (ChoiceGroupNotFoundError, distinct from ChoiceOptionNotFoundError).
        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": 999999, "choice_option_id": option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 404

    async def test_duplicate_option_in_same_request_returns_409(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Athletics", ability="STR")
        feature = await create_feature(name="Double Pick", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 2,
                        "choice_type": "SKILL",
                        "options": [
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                            {"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        # Same option_id picked twice for the same group in one request.
        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={
                "answers": [
                    {"choice_group_id": group_id, "choice_option_id": option_id},
                    {"choice_group_id": group_id, "choice_option_id": option_id},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
class TestGmGrantInlineChoices:
    async def test_gm_add_feature_with_inline_choices_applies_immediately(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        """
        GM-panel feature grants accept ``choices`` in the same request
        (``enforce=False``): a fully answered set applies right away,
        with no pending group left afterward.
        """

        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Insight", ability="WIS")
        feature = await create_feature(name="Instant Pick", source_type="CLASS", level=None)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        group_id = cg_resp.json()[0]["id"]
        option_id = cg_resp.json()[0]["options"][0]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={
                "feature_id": feature.id,
                "choices": [{"choice_group_id": group_id, "choice_option_id": option_id}],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        pending_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert pending_resp.json()["groups"] == []

        prof_resp = await client.get(
            f"/characters/{character.id}/proficiencies",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        skill_ids = [s["skill_id"] for s in prof_resp.json()["skills"]]
        assert skill.id in skill_ids

    async def test_gm_add_feature_without_choices_leaves_it_pending_not_rejected(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        """A GM feature grant with no answers lands (201) with the group left pending — never rejected."""

        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Perception", ability="WIS")
        feature = await create_feature(name="Deferred Pick", source_type="CLASS", level=None)

        await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201, grant_resp.text
        cf_id = grant_resp.json()["id"]

        pending_resp = await client.get(
            f"/characters/{character.id}/features/{cf_id}/choices",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert len(pending_resp.json()["groups"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestAllPendingChoicesSurface:
    async def test_get_all_pending_choices_lists_only_grants_with_unanswered_groups(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_skill
    ):
        feature_class = await create_class(name="Rogue")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        skill = await create_skill(name="Survival", ability="WIS")

        pending_feature = await create_feature(name="Unanswered", source_type="CLASS", level=None)
        await client.put(
            f"/features/{pending_feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        no_choice_feature = await create_feature(name="No Choices", source_type="CLASS", level=None)

        pending_grant = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": pending_feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert pending_grant.status_code == 201, pending_grant.text
        answered_grant = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": no_choice_feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answered_grant.status_code == 201, answered_grant.text

        response = await client.get(
            f"/characters/{character.id}/grants/pending",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["feature_id"] == pending_feature.id
        assert body[0]["feature_name"] == "Unanswered"
        assert len(body[0]["groups"]) == 1

    async def test_get_all_pending_choices_empty_when_nothing_pending(
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

        response = await client.get(
            f"/characters/{character.id}/grants/pending",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellResolutionEdgeCases:
    async def test_open_spell_resolved_to_nonexistent_spell_id_returns_422(
        self, client, gm, gm_token, create_class, create_character, create_feature, db_session
    ):
        feature_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Spell Pick", source_type="CLASS", level=None)

        # Pre-existing open ("any") spell effect (spell_id=null) — authoring one
        # via the API is rejected now, so this is seeded directly.
        group_id, option_id = await _seed_open_spell_choice_group(db_session, feature.id)

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        ans = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": option_id, "spell_id": 999999}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        # The option is rejected as unconditionally open before spell_id is
        # even looked up, so a nonexistent id gets the same "open" 422, not
        # a not-found error.
        assert ans.status_code == 422
        assert "open" in ans.json()["error"]["message"]

    async def test_reanswer_removes_stale_granted_spell(
        self, client, gm, gm_token, create_class, create_character, create_feature, create_spell
    ):
        feature_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id)
        feature = await create_feature(name="Spell Swap", source_type="CLASS", level=None)

        fireball = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")
        cure_wounds = await create_spell(name="Cure Wounds", school="EVOCATION", level="LEVEL_1")

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SPELL",
                        "options": [
                            {"effects": [{"effect_type": "spell", "items": [{"spell_id": fireball.id}]}]},
                            {"effects": [{"effect_type": "spell", "items": [{"spell_id": cure_wounds.id}]}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        group_id = cg_resp.json()[0]["id"]
        fireball_option_id = cg_resp.json()[0]["options"][0]["id"]
        cure_wounds_option_id = cg_resp.json()[0]["options"][1]["id"]

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        cf_id = grant_resp.json()["id"]

        ans1 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": fireball_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans1.status_code == 200
        first_spells = (
            await client.get(f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()["feature_spells"]
        assert [s["id"] for s in first_spells] == [fireball.id]

        ans2 = await client.patch(
            f"/characters/{character.id}/features/{cf_id}/choices",
            json={"answers": [{"choice_group_id": group_id, "choice_option_id": cure_wounds_option_id}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ans2.status_code == 200
        second_spells = (
            await client.get(f"/characters/{character.id}/spells", headers={"Authorization": f"Bearer {gm_token}"})
        ).json()["feature_spells"]
        assert [s["id"] for s in second_spells] == [cure_wounds.id]
