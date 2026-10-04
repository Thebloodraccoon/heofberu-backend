"""Invalid effect-engine input: proper 4xx instead of a misleading 409/500, no silent wipes, has_* invariant."""

import pytest
from sqlalchemy import func, select

from app.models import Feature
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureArmorProficiencyEffect,
    FeatureChoiceGroup,
    FeatureSavingThrowEffect,
    FeatureSkillProficiencyEffect,
    FeatureSpellGrantEffect,
    FeatureWeaponProficiencyEffect,
)

FIXED_EFFECT_MODELS = (
    FeatureAbilityScoreEffect,
    FeatureSkillProficiencyEffect,
    FeatureSavingThrowEffect,
    FeatureArmorProficiencyEffect,
    FeatureWeaponProficiencyEffect,
    FeatureSpellGrantEffect,
)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def put_effects(client, token, feature_id, payload):
    return await client.put(f"/features/{feature_id}/effects", json=payload, headers=auth(token))


async def put_groups(client, token, feature_id, groups):
    return await client.put(
        f"/features/{feature_id}/choice-groups", json={"choice_groups": groups}, headers=auth(token)
    )


def group_of(choice_type, options, **extra):
    return {"pick_count": 1, "choice_type": choice_type, "options": options, **extra}


async def assert_flags_match_tables(db_session, feature_id):
    """The denormalized ``has_*`` columns must equal what the effect tables actually hold."""

    db_session.expire_all()
    feature = (await db_session.execute(select(Feature).where(Feature.id == feature_id))).scalar_one()

    has_static = False
    for model in FIXED_EFFECT_MODELS:
        count = await db_session.scalar(select(func.count()).select_from(model).where(model.feature_id == feature_id))
        has_static = has_static or bool(count)
    has_groups = bool(
        await db_session.scalar(
            select(func.count()).select_from(FeatureChoiceGroup).where(FeatureChoiceGroup.feature_id == feature_id)
        )
    )

    assert feature.has_static_effects is has_static
    assert feature.has_choices is has_groups


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroupInputIsRejectedWithA4xx:
    @pytest.mark.parametrize("pick_count", [0, -1])
    async def test_non_positive_pick_count_is_422_not_a_misleading_409(
        self, client, gm_token, create_feature, create_skill, pick_count
    ):
        feature = await create_feature(name="Skilled")
        skill = await create_skill(name="Stealth")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [
                {
                    **group_of("SKILL", [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]}]),
                    "pick_count": pick_count,
                }
            ],
        )

        assert response.status_code == 422

    async def test_unknown_skill_id_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Skilled")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [group_of("SKILL", [{"effects": [{"effect_type": "skill", "items": [{"skill_id": 987654}]}]}])],
        )

        assert response.status_code == 422
        assert "987654" in response.text
        assert (await client.get(f"/features/{feature.id}/choice-groups")).json() == []

    async def test_unknown_spell_id_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Caster")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [group_of("SPELL", [{"effects": [{"effect_type": "spell", "items": [{"spell_id": 424242}]}]}])],
        )

        assert response.status_code == 422

    async def test_unknown_item_id_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Armed")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [group_of("WEAPON", [{"effects": [{"effect_type": "weapon", "items": [{"item_id": 31337}]}]}])],
        )

        assert response.status_code == 422

    async def test_oversized_catalog_id_is_422_not_a_driver_overflow(self, client, gm_token, create_feature):
        feature = await create_feature(name="Skilled")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [group_of("SKILL", [{"effects": [{"effect_type": "skill", "items": [{"skill_id": 2**40}]}]}])],
        )

        assert response.status_code == 422

    async def test_missing_choice_groups_key_is_422_and_wipes_nothing(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")
        await put_groups(
            client,
            gm_token,
            feature.id,
            [
                group_of(
                    "ABILITY_SCORE",
                    [{"effects": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]}],
                )
            ],
        )

        response = await client.put(f"/features/{feature.id}/choice-groups", json={}, headers=auth(gm_token))

        assert response.status_code == 422
        assert len((await client.get(f"/features/{feature.id}/choice-groups")).json()) == 1

    async def test_unknown_key_in_a_group_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")

        response = await put_groups(client, gm_token, feature.id, [group_of("SKILL", [], pickcount=2)])

        assert response.status_code == 422

    async def test_legacy_group_label_is_accepted_and_dropped(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")

        response = await put_groups(client, gm_token, feature.id, [group_of("SKILL", [], label="Old client")])

        assert response.status_code == 200
        assert "label" not in response.json()[0]

    async def test_duplicate_effect_in_one_option_is_422(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Skilled")
        skill = await create_skill(name="Stealth")

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [
                group_of(
                    "SKILL",
                    [
                        {
                            "effects": [
                                {"effect_type": "skill", "items": [{"skill_id": skill.id}, {"skill_id": skill.id}]}
                            ]
                        }
                    ],
                )
            ],
        )

        assert response.status_code == 422

    async def test_duplicate_option_ids_are_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")
        created = await put_groups(
            client,
            gm_token,
            feature.id,
            [
                group_of(
                    "ABILITY_SCORE",
                    [{"effects": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]}],
                )
            ],
        )
        group = created.json()[0]
        option_id = group["options"][0]["id"]

        response = await put_groups(
            client,
            gm_token,
            feature.id,
            [
                group_of(
                    "ABILITY_SCORE",
                    [{"id": option_id, "effects": []}, {"id": option_id, "effects": []}],
                    id=group["id"],
                )
            ],
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestFixedEffectInput:
    async def test_fixed_skill_without_skill_id_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Skilled")

        response = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "skill", "items": [{"grants_expertise": True}]}]},
        )

        assert response.status_code == 422

    async def test_unknown_skill_id_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Skilled")

        response = await put_effects(
            client, gm_token, feature.id, {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": 555555}]}]}
        )

        assert response.status_code == 422
        assert "555555" in response.text

    async def test_unknown_item_and_spell_ids_are_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Armed")

        assert (
            await put_effects(
                client,
                gm_token,
                feature.id,
                {"static_groups": [{"effect_type": "weapon", "items": [{"item_id": 4040}]}]},
            )
        ).status_code == 422
        assert (
            await put_effects(
                client,
                gm_token,
                feature.id,
                {"static_groups": [{"effect_type": "spell", "items": [{"spell_id": 4041}]}]},
            )
        ).status_code == 422

    async def test_duplicate_skill_is_422(self, client, gm_token, create_feature, create_skill):
        feature = await create_feature(name="Skilled")
        skill = await create_skill(name="Stealth")

        response = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill.id}, {"skill_id": skill.id}]}]},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("field", "items"),
        [
            ("saving_throw_effects", [{"ability": "WIS"}, {"ability": "WIS"}]),
            ("armor_effects", [{"armor_type": "HEAVY"}, {"armor_type": "HEAVY"}]),
            ("weapon_effects", [{"weapon_category": "MARTIAL"}, {"weapon_category": "MARTIAL"}]),
        ],
    )
    async def test_duplicate_effects_of_every_type_are_422(self, client, gm_token, create_feature, field, items):
        feature = await create_feature(name="Dupes")

        payload = {"static_groups": [{"effect_type": field.removesuffix("_effects"), "items": items}]}
        response = await put_effects(client, gm_token, feature.id, payload)

        assert response.status_code == 422

    async def test_same_row_id_twice_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Dupes")
        created = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
        )
        row_id = created.json()["static_groups"][0]["items"][0]["id"]

        response = await put_effects(
            client,
            gm_token,
            feature.id,
            {
                "static_groups": [
                    {
                        "effect_type": "armor",
                        "items": [{"id": row_id, "armor_type": "LIGHT"}, {"id": row_id, "armor_type": "HEAVY"}],
                    }
                ]
            },
        )

        assert response.status_code == 422

    async def test_out_of_range_amount_is_422_not_a_database_error(self, client, gm_token, create_feature):
        feature = await create_feature(name="Huge")

        response = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 2**33}]}]},
        )

        assert response.status_code == 422

    async def test_unknown_key_is_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Typo")

        response = await put_effects(client, gm_token, feature.id, {"armor_effect": [{"armor_type": "LIGHT"}]})

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestPutEffectsDoesNotWipeOmittedTypes:
    async def test_omitted_effect_types_are_left_untouched(self, client, gm_token, create_feature):
        feature = await create_feature(name="Mixed")
        await put_effects(
            client,
            gm_token,
            feature.id,
            {
                "static_groups": [
                    {"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]},
                    {"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]},
                ]
            },
        )

        response = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "weapon", "items": [{"weapon_category": "SIMPLE"}]}]},
        )

        assert response.status_code == 200
        types = {group["effect_type"] for group in response.json()["static_groups"]}
        assert types == {"ability", "armor", "weapon"}

    async def test_empty_list_clears_just_that_type(self, client, gm_token, create_feature):
        feature = await create_feature(name="Mixed")
        await put_effects(
            client,
            gm_token,
            feature.id,
            {
                "static_groups": [
                    {"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]},
                    {"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]},
                ]
            },
        )

        response = await put_effects(
            client, gm_token, feature.id, {"static_groups": [{"effect_type": "armor", "items": []}]}
        )

        assert {group["effect_type"] for group in response.json()["static_groups"]} == {"ability"}

    async def test_empty_body_is_a_no_op(self, client, gm_token, create_feature):
        feature = await create_feature(name="Mixed")
        await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
        )

        response = await put_effects(client, gm_token, feature.id, {})

        assert response.status_code == 200
        assert [group["effect_type"] for group in response.json()["static_groups"]] == ["armor"]

    async def test_resending_the_same_tree_keeps_row_ids(self, client, gm_token, create_feature):
        feature = await create_feature(name="Stable")
        first = await put_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
        )
        items = first.json()["static_groups"][0]["items"]

        second = await put_effects(
            client, gm_token, feature.id, {"static_groups": [{"effect_type": "armor", "items": items}]}
        )

        assert second.status_code == 200
        assert second.json()["static_groups"][0]["items"] == items


@pytest.mark.integration
@pytest.mark.asyncio
class TestEffectFlagsInvariant:
    async def test_flags_follow_every_kind_of_write(self, client, gm_token, db_session, create_feature, create_skill):
        feature_id = (await create_feature(name="Flags", source_type="OTHER")).id
        skill_id = (await create_skill(name="Stealth")).id
        await assert_flags_match_tables(db_session, feature_id)

        await put_effects(
            client,
            gm_token,
            feature_id,
            {"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
        )
        await assert_flags_match_tables(db_session, feature_id)

        await put_groups(
            client,
            gm_token,
            feature_id,
            [group_of("SKILL", [{"effects": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]}])],
        )
        await assert_flags_match_tables(db_session, feature_id)

        await put_effects(client, gm_token, feature_id, {"static_groups": [{"effect_type": "armor", "items": []}]})
        await assert_flags_match_tables(db_session, feature_id)

        await put_groups(client, gm_token, feature_id, [])
        await assert_flags_match_tables(db_session, feature_id)

        listing = await client.get("/features", params={"search": "Flags"})
        entry = next(item for item in listing.json()["items"] if item["id"] == feature_id)
        assert entry["has_static_effects"] is False
        assert entry["has_choices"] is False

    async def test_failed_write_leaves_flags_and_rows_untouched(self, client, gm_token, db_session, create_feature):
        feature_id = (await create_feature(name="Atomic")).id
        await put_effects(
            client,
            gm_token,
            feature_id,
            {"static_groups": [{"effect_type": "armor", "items": [{"armor_type": "LIGHT"}]}]},
        )

        response = await put_effects(
            client,
            gm_token,
            feature_id,
            {
                "static_groups": [
                    {"effect_type": "armor", "items": []},
                    {"effect_type": "weapon", "items": [{"item_id": 99999}]},
                ]
            },
        )

        assert response.status_code == 422
        await assert_flags_match_tables(db_session, feature_id)
        assert [
            g["effect_type"] for g in (await client.get(f"/features/{feature_id}/effects")).json()["static_groups"]
        ] == ["armor"]
