"""
Progression/grants rules added in the hardening pass: feat limits at level-up, the ASI log on
revoke and rebuild, authorization of the grant endpoints, and cache freshness after answering.
"""

import pytest

from tests.integration.features.characters.test_progression import level_up_to


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def author_asi_options(client, gm_token, feat, abilities=("STR",)):
    """Give a feat one ABILITY_SCORE group with a +1 option per ability; return the ASI effect ids in order."""
    response = await client.put(
        f"/feats/{feat.id}/choice-groups",
        json={
            "choice_groups": [
                {
                    "pick_count": 1,
                    "choice_type": "ABILITY_SCORE",
                    "options": [{"ability_effects": [{"ability": ability, "amount": 1}]} for ability in abilities],
                }
            ]
        },
        headers=auth(gm_token),
    )
    assert response.status_code == 200, response.text
    return [option["ability_effects"][0]["id"] for option in response.json()[0]["options"]]


async def level_up_with(client, token, character_id, choice):
    return await client.post(
        f"/characters/{character_id}/progression/level-up",
        json={"choice": choice},
        headers=auth(token),
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatRulesAtLevelUp:
    async def test_feat_below_its_min_level_is_rejected_and_nothing_is_written(
        self, client, player, player_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character_id = (await create_character(owner_id=player.id, class_id=fighter.id, level=3)).id
        feat = await create_feat(name="Heavy Armor Master", min_level=8)

        response = await level_up_with(client, player_token, character_id, {"type": "FEAT", "feat_id": feat.id})

        assert response.status_code == 400
        assert (await client.get(f"/characters/{character_id}", headers=auth(player_token))).json()["level"] == 3
        assert (await client.get(f"/characters/{character_id}/feats", headers=auth(player_token))).json() == []

    async def test_feat_at_its_min_level_is_granted(
        self, client, player, player_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character = await create_character(owner_id=player.id, class_id=fighter.id, level=3)
        feat = await create_feat(name="Tough", min_level=4)

        response = await level_up_with(client, player_token, character.id, {"type": "FEAT", "feat_id": feat.id})

        assert response.status_code == 200, response.text

    async def test_feat_asi_option_cannot_push_a_score_above_twenty(
        self, client, player, player_token, gm_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character_id = (await create_character(owner_id=player.id, class_id=fighter.id, level=3, strength=20)).id
        feat = await create_feat(name="Athlete")
        (asi_id,) = await author_asi_options(client, gm_token, feat)

        response = await level_up_with(
            client,
            player_token,
            character_id,
            {"type": "FEAT", "feat_id": feat.id, "ability_score_increase_id": asi_id},
        )

        assert response.status_code == 400
        assert (await client.get(f"/characters/{character_id}", headers=auth(player_token))).json()["level"] == 3
        assert (await client.get(f"/characters/{character_id}/feats", headers=auth(player_token))).json() == []

    async def test_feat_asi_option_reaching_exactly_twenty_is_granted(
        self, client, player, player_token, gm_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character = await create_character(owner_id=player.id, class_id=fighter.id, level=3, strength=19)
        feat = await create_feat(name="Athlete")
        (asi_id,) = await author_asi_options(client, gm_token, feat)

        response = await level_up_with(
            client,
            player_token,
            character.id,
            {"type": "FEAT", "feat_id": feat.id, "ability_score_increase_id": asi_id},
        )

        assert response.status_code == 200, response.text
        assert response.json()["ability_scores"]["strength_total"] == 20


@pytest.mark.integration
@pytest.mark.asyncio
class TestAsiLogOnFeatRevoke:
    async def test_revoking_an_asi_feat_clears_its_log_row_and_unpins_the_feat(
        self, client, player, player_token, gm_token, founder_token, create_class, create_api_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=fighter.id, owner=player, strength=13)
        await level_up_to(client, player_token, character["id"], 3)
        feat = await create_feat(name="Resilient")
        (asi_id,) = await author_asi_options(client, gm_token, feat)
        response = await level_up_with(
            client,
            player_token,
            character["id"],
            {"type": "FEAT", "feat_id": feat.id, "ability_score_increase_id": asi_id},
        )
        assert response.status_code == 200, response.text
        log = (
            await client.get(f"/characters/{character['id']}/progression/asi-choices", headers=auth(gm_token))
        ).json()
        assert [(row["class_level"], row["feat_id"]) for row in log] == [(4, feat.id)]

        grant_id = (await client.get(f"/characters/{character['id']}/feats", headers=auth(gm_token))).json()[0]["id"]
        revoke = await client.delete(
            f"/characters/{character['id']}/gm-panel/feats", params={"feat_id": grant_id}, headers=auth(gm_token)
        )

        assert revoke.status_code == 204
        assert (
            await client.get(f"/characters/{character['id']}/progression/asi-choices", headers=auth(gm_token))
        ).json() == []
        # Nothing references the feat any more: removing it from the catalog is a clean 204, not a RESTRICT failure.
        deleted = await client.delete(f"/feats/{feat.id}", headers=auth(founder_token))
        assert deleted.status_code == 204, deleted.text

    async def test_revoking_a_gm_granted_feat_clears_its_audit_row(
        self, client, gm, gm_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=fighter.id)
        feat = await create_feat(name="Alert")
        grant = await client.post(
            f"/characters/{character.id}/gm-panel/feats", json={"feat_id": feat.id}, headers=auth(gm_token)
        )
        assert grant.status_code == 201
        assert (
            len(
                (await client.get(f"/characters/{character.id}/progression/asi-choices", headers=auth(gm_token))).json()
            )
            == 1
        )

        await client.delete(
            f"/characters/{character.id}/gm-panel/feats", params={"feat_id": grant.json()["id"]}, headers=auth(gm_token)
        )

        assert (
            await client.get(f"/characters/{character.id}/progression/asi-choices", headers=auth(gm_token))
        ).json() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatAsiUpdateKeepsOtherPicks:
    async def test_changing_the_asi_option_keeps_the_picks_of_other_groups(
        self, client, gm, gm_token, create_class, create_character, create_feat
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=fighter.id)
        feat = await create_feat(name="Defensive Duelist")
        response = await client.put(
            f"/feats/{feat.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [
                            {"ability_effects": [{"ability": "STR", "amount": 1}]},
                            {"ability_effects": [{"ability": "DEX", "amount": 1}]},
                        ],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SAVING_THROW",
                        "options": [{"saving_throw_effects": [{"ability": "WIS"}]}],
                    },
                ]
            },
            headers=auth(gm_token),
        )
        assert response.status_code == 200, response.text
        asi_group, save_group = response.json()
        str_id, dex_id = (option["ability_effects"][0]["id"] for option in asi_group["options"])

        grant = await client.post(
            f"/characters/{character.id}/gm-panel/feats",
            json={
                "feat_id": feat.id,
                "ability_score_increase_id": str_id,
                "choices": [{"choice_group_id": save_group["id"], "choice_option_id": save_group["options"][0]["id"]}],
            },
            headers=auth(gm_token),
        )
        assert grant.status_code == 201, grant.text

        update = await client.patch(
            f"/characters/{character.id}/gm-panel/feats",
            params={"feat_id": grant.json()["id"]},
            json={"ability_score_increase_id": dex_id},
            headers=auth(gm_token),
        )

        assert update.status_code == 200, update.text
        picked_groups = {choice["choice_group_id"]: choice["choice_option_id"] for choice in update.json()["choices"]}
        assert picked_groups == {
            asi_group["id"]: asi_group["options"][1]["id"],
            save_group["id"]: save_group["options"][0]["id"],
        }


@pytest.mark.integration
@pytest.mark.asyncio
class TestRebuildAsiHistory:
    async def rebuild_payload(self, fighter, elf, **overrides):
        payload = {
            "class_id": fighter.id,
            "race_id": elf.id,
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
            "max_hp": 10,
            "asi_choices": [],
        }
        payload.update(overrides)
        return payload

    async def test_rebuild_keeps_gm_adjustments(
        self, client, player, player_token, gm_token, create_class, create_race, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        elf = await create_race(name="Elf")
        character, _ = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id)
        adjustment = await client.post(
            f"/characters/{character['id']}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 3}]},
            headers=auth(gm_token),
        )
        assert adjustment.status_code == 201, adjustment.text

        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            json=await self.rebuild_payload(fighter, elf),
            headers=auth(player_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["ability_scores"]["strength_total"] == 13
        log = (
            await client.get(f"/characters/{character['id']}/progression/asi-choices", headers=auth(gm_token))
        ).json()
        assert [(row["class_level"], row["increases"]) for row in log] == [(None, [{"ability": "STR", "amount": 3}])]

    async def test_rebuild_replaces_level_choices_but_keeps_gm_adjustments(
        self, client, player, player_token, gm_token, create_class, create_race, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        elf = await create_race(name="Elf")
        character, _ = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id)
        character_id = character["id"]
        await level_up_to(client, player_token, character_id, 3)
        assert (
            await level_up_with(
                client, player_token, character_id, {"type": "ASI", "increases": [{"ability": "DEX", "amount": 2}]}
            )
        ).status_code == 200
        await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 3}]},
            headers=auth(gm_token),
        )

        response = await client.post(
            f"/characters/{character_id}/rebuild",
            json=await self.rebuild_payload(
                fighter,
                elf,
                max_hp=40,
                asi_choices=[
                    {"class_level": 4, "choice": {"type": "ASI", "increases": [{"ability": "CON", "amount": 2}]}}
                ],
            ),
            headers=auth(player_token),
        )

        assert response.status_code == 200, response.text
        scores = response.json()["ability_scores"]
        assert (scores["strength_total"], scores["dexterity_total"], scores["constitution_total"]) == (13, 10, 12)
        log = (await client.get(f"/characters/{character_id}/progression/asi-choices", headers=auth(gm_token))).json()
        assert sorted((row["class_level"] is None, row["increases"][0]["ability"]) for row in log) == [
            (False, "CON"),
            (True, "STR"),
        ]

    async def test_rebuild_rejects_an_asi_feat_without_its_ability_pick(
        self, client, player, player_token, gm_token, create_class, create_race, create_api_character, create_feat
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        elf = await create_race(name="Elf")
        character, _ = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id)
        character_id = character["id"]
        await level_up_to(client, player_token, character_id, 3)
        assert (
            await level_up_with(
                client, player_token, character_id, {"type": "ASI", "increases": [{"ability": "DEX", "amount": 2}]}
            )
        ).status_code == 200
        feat = await create_feat(name="Resilient")
        await author_asi_options(client, gm_token, feat)

        response = await client.post(
            f"/characters/{character_id}/rebuild",
            json=await self.rebuild_payload(
                fighter,
                elf,
                max_hp=40,
                asi_choices=[{"class_level": 4, "choice": {"type": "FEAT", "feat_id": feat.id}}],
            ),
            headers=auth(player_token),
        )

        assert response.status_code == 422, response.text
        # The failed rebuild rolled back: the original level-4 ASI is still on record.
        log = (await client.get(f"/characters/{character_id}/progression/asi-choices", headers=auth(gm_token))).json()
        assert [(row["class_level"], row["choice_type"]) for row in log] == [(4, "ASI")]


async def feature_with_ability_choice(client, gm_token, create_feature, class_id, abilities=("STR", "DEX")):
    """A level-1 CLASS feature with one "pick one" ABILITY_SCORE group; return (feature, group, options)."""
    feature = await create_feature(name="Gifted", source_type="CLASS", class_id=class_id, level=1)
    response = await client.put(
        f"/features/{feature.id}/choice-groups",
        json={
            "choice_groups": [
                {
                    "pick_count": 1,
                    "choice_type": "ABILITY_SCORE",
                    "options": [{"ability_effects": [{"ability": ability, "amount": 1}]} for ability in abilities],
                }
            ]
        },
        headers=auth(gm_token),
    )
    assert response.status_code == 200, response.text
    group = response.json()[0]
    return feature, group, group["options"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGrantEndpointsAuthorization:
    async def test_a_stranger_gets_403_on_every_grant_read_and_write(
        self, client, player, gm_token, create_user, login_as, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        _, group, options = await feature_with_ability_choice(client, gm_token, create_feature, fighter.id)
        character, owner_token = await create_api_character(class_id=fighter.id, owner=player)
        character_id = character["id"]
        grant_id = (await client.get(f"/characters/{character_id}/features", headers=auth(owner_token))).json()[0]["id"]
        stranger_token = await login_as(await create_user(role="PLAYER"))
        base = f"/characters/{character_id}"

        reads = [
            f"{base}/features",
            f"{base}/feats",
            f"{base}/grants/pending",
            f"{base}/grants/answered",
            f"{base}/features/{grant_id}/choices",
            f"{base}/features/{grant_id}/choices/answered",
        ]
        for url in reads:
            response = await client.get(url, headers=auth(stranger_token))
            assert response.status_code == 403, url
            assert (await client.get(url, headers=auth(owner_token))).status_code == 200, url

        answer = await client.patch(
            f"{base}/features/{grant_id}/choices",
            json={"answers": [{"choice_group_id": group["id"], "choice_option_id": options[0]["id"]}]},
            headers=auth(stranger_token),
        )
        assert answer.status_code == 403
        still_pending = await client.get(f"{base}/grants/pending", headers=auth(owner_token))
        assert [item["character_feature_id"] for item in still_pending.json()] == [grant_id]

    async def test_a_grant_of_another_character_is_not_reachable_through_your_own(
        self, client, player, gm_token, create_user, login_as, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        _, _, _ = await feature_with_ability_choice(client, gm_token, create_feature, fighter.id)
        mine, my_token = await create_api_character(class_id=fighter.id, owner=player)
        other_owner = await create_user()
        theirs, their_token = await create_api_character(class_id=fighter.id, owner=other_owner)
        their_grant = (await client.get(f"/characters/{theirs['id']}/features", headers=auth(their_token))).json()[0][
            "id"
        ]

        response = await client.get(f"/characters/{mine['id']}/features/{their_grant}/choices", headers=auth(my_token))

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnswerChoices:
    async def test_re_answering_refreshes_the_cached_character_after_commit(
        self, client, player, gm_token, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        _, group, options = await feature_with_ability_choice(client, gm_token, create_feature, fighter.id)
        character, token = await create_api_character(class_id=fighter.id, owner=player, strength=10, dexterity=10)
        character_id = character["id"]
        grant_id = (await client.get(f"/characters/{character_id}/features", headers=auth(token))).json()[0]["id"]
        url = f"/characters/{character_id}/features/{grant_id}/choices"

        first = await client.patch(
            url,
            json={"answers": [{"choice_group_id": group["id"], "choice_option_id": options[0]["id"]}]},
            headers=auth(token),
        )
        assert first.status_code == 200 and first.json()["groups"] == []
        cached = (await client.get(f"/characters/{character_id}", headers=auth(token))).json()["ability_scores"]
        assert (cached["strength_total"], cached["dexterity_total"]) == (11, 10)

        second = await client.patch(
            url,
            json={"answers": [{"choice_group_id": group["id"], "choice_option_id": options[1]["id"]}]},
            headers=auth(token),
        )

        assert second.status_code == 200
        fresh = (await client.get(f"/characters/{character_id}", headers=auth(token))).json()["ability_scores"]
        assert (fresh["strength_total"], fresh["dexterity_total"]) == (10, 11)
        answered = (await client.get(f"{url}/answered", headers=auth(token))).json()
        assert [choice["choice_option_id"] for choice in answered["choices"]] == [options[1]["id"]]

    async def test_a_failed_answer_changes_nothing(
        self, client, player, gm_token, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        _, group, options = await feature_with_ability_choice(client, gm_token, create_feature, fighter.id)
        character, token = await create_api_character(class_id=fighter.id, owner=player)
        grant_id = (await client.get(f"/characters/{character['id']}/features", headers=auth(token))).json()[0]["id"]
        url = f"/characters/{character['id']}/features/{grant_id}/choices"

        response = await client.patch(
            url,
            json={"answers": [{"choice_group_id": group["id"], "choice_option_id": o["id"]} for o in options]},
            headers=auth(token),
        )

        assert response.status_code == 422
        assert (await client.get(f"{url}/answered", headers=auth(token))).json()["choices"] == []

    async def test_an_oversized_answer_list_is_a_422(
        self, client, player, gm_token, create_class, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=fighter.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/features/1/choices",
            json={"answers": [{"choice_group_id": 1, "choice_option_id": i + 1} for i in range(60)]},
            headers=auth(token),
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestLevelUpBatchesFeatureChoices:
    async def test_two_features_unlocked_by_one_level_are_resolved_in_one_request(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        picks = []
        for name in ("Gift of Strength", "Gift of Grace"):
            feature = await create_feature(name=name, source_type="CLASS", class_id=fighter.id, level=2)
            response = await client.put(
                f"/features/{feature.id}/choice-groups",
                json={
                    "choice_groups": [
                        {
                            "pick_count": 1,
                            "choice_type": "ABILITY_SCORE",
                            "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                        }
                    ]
                },
                headers=auth(gm_token),
            )
            assert response.status_code == 200, response.text
            group = response.json()[0]
            picks.append(
                {
                    "feature_id": feature.id,
                    "choice_group_id": group["id"],
                    "choice_option_id": group["options"][0]["id"],
                }
            )
        character, _ = await create_api_character(class_id=fighter.id, owner=player, strength=10)
        url = f"/characters/{character['id']}/progression/level-up"

        partial = await client.post(url, json={"feature_choices": picks[:1]}, headers=auth(player_token))
        assert partial.status_code == 422
        assert (await client.get(f"/characters/{character['id']}", headers=auth(player_token))).json()["level"] == 1

        response = await client.post(url, json={"feature_choices": picks}, headers=auth(player_token))

        assert response.status_code == 200, response.text
        assert response.json()["level"] == 2
        assert response.json()["ability_scores"]["strength_total"] == 12
        pending = await client.get(f"/characters/{character['id']}/grants/pending", headers=auth(player_token))
        assert pending.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestProgressionPayloadBounds:
    async def test_oversized_ids_and_lists_are_rejected_with_422(
        self, client, player, player_token, create_class, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=fighter.id, owner=player)
        base = f"/characters/{character['id']}/progression"

        too_big_id = await client.patch(f"{base}/background", json={"background_id": 2**31}, headers=auth(player_token))
        too_many_choices = await client.post(
            f"{base}/level-up",
            json={"feature_choices": [{"feature_id": 1, "choice_group_id": 1, "choice_option_id": 1}] * 51},
            headers=auth(player_token),
        )
        absurd_hp = await client.post(
            f"{base}/level-up", json={"hit_points_gained": 10_000}, headers=auth(player_token)
        )

        assert (too_big_id.status_code, too_many_choices.status_code, absurd_hp.status_code) == (422, 422, 422)
