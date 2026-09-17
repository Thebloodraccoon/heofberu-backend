"""
Baseline coverage for the *multi-grant, same-character* materializer risks
that the ``characters-grant-materialization-batching-plan`` Variant A
refactor would introduce if the batched diff's key ever drops ``grant_id``.

Unlike ``test_grants_materializer_effects.py`` (single grant, re-answer
scenarios), these tests put TWO auto-grants (class + race) on one character
whose effects target the SAME skill, then assert on the *resulting,
per-grant materialized rows* — exactly what
``FeatureGrantMaterializer._own_rows``/``_reconcile_by_key`` must keep
correct if ``sync_progression_features``'s per-grant loop is ever collapsed
into one batched diff keyed by ``(grant_id, skill_id)`` instead of scoped
per grant by construction (see ``materializer.py``'s class docstring: two
sources granting the same proficiency is two legitimate rows, and
``is_expertise`` upgrades are monotonic per row, never merged across rows).

Read via ``GET /characters/{id}/features`` (``effects`` per grant, built by
``get_grant_effects_map`` keyed on ``grant.id``) rather than
``GET /characters/{id}/proficiencies``, which deliberately RESOLVES/merges
every source into one row per skill (``is_expertise`` is documented there as
"the OR across all of them") — that view would mask exactly the per-row
corruption these tests exist to catch.

Must pass against the CURRENT unbatched code (one query per grant) before
any Variant A refactor starts, and must still pass after.
"""

import pytest


def _grant_for_feature(grants: list[dict], feature_id: int) -> dict:
    return next(g for g in grants if g["feature_id"] == feature_id)


def _skill_row(grant: dict, skill_id: int) -> dict:
    return next(s for s in grant["effects"]["skills"] if s["skill_id"] == skill_id)


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiGrantDedup:
    async def test_two_auto_grants_sharing_a_skill_each_materialize_their_own_row(
        self,
        client,
        gm_token,
        create_class,
        create_race,
        create_api_character,
        create_feature,
        create_skill,
    ):
        """
        Class feature and race feature both grant proficiency in the SAME
        skill — both auto-grant in the same ``sync_progression_features``
        call at character creation. Each grant must materialize its OWN
        skill row; a batched diff keyed only on ``skill_id`` (dropping
        ``grant_id``) could plausibly let one grant's insert clobber or skip
        the other's.
        """

        skill = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Human")

        class_feature = await create_feature(
            name="Keen Senses (Class)", source_type="CLASS", class_id=character_class.id, level=None
        )
        race_feature = await create_feature(
            name="Keen Senses (Race)", source_type="RACE", race_id=race.id, level=None
        )

        for feature in (class_feature, race_feature):
            fx_resp = await client.put(
                f"/features/{feature.id}/effects",
                json={"skill_effects": [{"skill_id": skill.id, "grants_expertise": False}]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert fx_resp.status_code == 200, fx_resp.text

        character, token = await create_api_character(class_id=character_class.id, race_id=race.id)

        grants_resp = await client.get(
            f"/characters/{character['id']}/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert grants_resp.status_code == 200
        grants = grants_resp.json()

        class_grant = _grant_for_feature(grants, class_feature.id)
        race_grant = _grant_for_feature(grants, race_feature.id)

        assert _skill_row(class_grant, skill.id)["is_expertise"] is False
        assert _skill_row(race_grant, skill.id)["is_expertise"] is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiGrantExpertiseIndependence:
    async def test_two_auto_grants_one_expertise_one_not_stay_independent(
        self,
        client,
        gm_token,
        create_class,
        create_race,
        create_api_character,
        create_feature,
        create_skill,
    ):
        """
        Class feature grants the skill WITH expertise, race feature grants
        the SAME skill withOUT expertise — both materialize in the same
        multi-grant sync. Each grant's own row must keep its own
        ``is_expertise`` state; neither must leak into the other (a batched
        diff that groups by ``skill_id`` alone, instead of
        ``(grant_id, skill_id)``, could plausibly let the wrong grant's
        ``on_keep`` touch the other's row, or merge/OR them).
        """

        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        character_class = await create_class(name="Rogue")
        race = await create_race(name="Halfling")

        class_feature = await create_feature(
            name="Trained Stealth (Class)", source_type="CLASS", class_id=character_class.id, level=None
        )
        race_feature = await create_feature(
            name="Natural Stealth (Race)", source_type="RACE", race_id=race.id, level=None
        )

        class_fx = await client.put(
            f"/features/{class_feature.id}/effects",
            json={"skill_effects": [{"skill_id": skill.id, "grants_expertise": True}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert class_fx.status_code == 200, class_fx.text

        race_fx = await client.put(
            f"/features/{race_feature.id}/effects",
            json={"skill_effects": [{"skill_id": skill.id, "grants_expertise": False}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert race_fx.status_code == 200, race_fx.text

        character, token = await create_api_character(class_id=character_class.id, race_id=race.id)

        grants_resp = await client.get(
            f"/characters/{character['id']}/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert grants_resp.status_code == 200
        grants = grants_resp.json()

        class_grant = _grant_for_feature(grants, class_feature.id)
        race_grant = _grant_for_feature(grants, race_feature.id)

        assert _skill_row(class_grant, skill.id)["is_expertise"] is True
        assert _skill_row(race_grant, skill.id)["is_expertise"] is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiGrantSyncPreservesSiblingRows:
    async def test_leveling_up_adds_new_grant_without_disturbing_existing_sibling_grant_row(
        self,
        client,
        gm_token,
        create_class,
        create_race,
        create_api_character,
        create_feature,
        create_skill,
    ):
        """
        A race feature (ungated, present from level 1) grants a skill
        without expertise. A class feature gated at level 3 grants the SAME
        skill WITH expertise. Leveling from 1 to 3 re-runs
        ``sync_progression_features`` with BOTH the pre-existing race grant
        and the newly-added class grant in ``all_auto_grants`` — the
        already-materialized race grant's row must survive untouched (not
        deleted, not merged, not have its ``is_expertise`` flipped) when the
        new class grant's row is added in the same call.
        """

        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        character_class = await create_class(name="Wizard")
        race = await create_race(name="Gnome")

        race_feature = await create_feature(name="Gnomish Cunning", source_type="RACE", race_id=race.id, level=None)
        race_fx = await client.put(
            f"/features/{race_feature.id}/effects",
            json={"skill_effects": [{"skill_id": skill.id, "grants_expertise": False}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert race_fx.status_code == 200, race_fx.text

        class_feature = await create_feature(
            name="Arcane Focus", source_type="CLASS", class_id=character_class.id, level=3
        )
        class_fx = await client.put(
            f"/features/{class_feature.id}/effects",
            json={"skill_effects": [{"skill_id": skill.id, "grants_expertise": True}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert class_fx.status_code == 200, class_fx.text

        character, token = await create_api_character(class_id=character_class.id, race_id=race.id)

        # Level 1: only the ungated race grant applies, no class grant yet.
        before_resp = await client.get(
            f"/characters/{character['id']}/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        before_grants = before_resp.json()
        assert not any(g["feature_id"] == class_feature.id for g in before_grants)
        race_grant_before = _grant_for_feature(before_grants, race_feature.id)
        assert _skill_row(race_grant_before, skill.id)["is_expertise"] is False

        # Plain level-ups (no ASI level crossed before 4) — this triggers
        # sync_progression_features with both grants present.
        for _ in range(2):
            level_up_resp = await client.post(
                f"/characters/{character['id']}/progression/level-up",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert level_up_resp.status_code == 200, level_up_resp.text

        after_resp = await client.get(
            f"/characters/{character['id']}/features",
            headers={"Authorization": f"Bearer {token}"},
        )
        after_grants = after_resp.json()

        race_grant_after = _grant_for_feature(after_grants, race_feature.id)
        class_grant_after = _grant_for_feature(after_grants, class_feature.id)

        assert race_grant_after["id"] == race_grant_before["id"], "the race grant itself must not be replaced"
        assert (
            _skill_row(race_grant_after, skill.id)["is_expertise"] is False
        ), "the race grant's row must not be upgraded by the sibling class grant"
        assert _skill_row(class_grant_after, skill.id)["is_expertise"] is True
