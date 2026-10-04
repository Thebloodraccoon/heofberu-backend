"""Feature delete/update lifecycle: in-use guard, one transaction, reconcile only when it matters, cache refresh."""

import pytest
from sqlalchemy import delete, select

from app.constants import GrantSource
from app.models import CharacterFeature, Feature


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def grant(db_session, character_id, feature_id, grant_source=GrantSource.GM):
    db_session.add(CharacterFeature(character_id=character_id, feature_id=feature_id, grant_source=grant_source))
    await db_session.commit()


async def revoke(db_session, character_id, feature_id):
    """Delete a grant row directly, bypassing every service."""

    await db_session.execute(
        delete(CharacterFeature).where(
            CharacterFeature.character_id == character_id, CharacterFeature.feature_id == feature_id
        )
    )
    await db_session.commit()


async def grants_of(db_session, character_id):
    db_session.expire_all()
    result = await db_session.execute(select(CharacterFeature).where(CharacterFeature.character_id == character_id))
    return {row.feature_id: row for row in result.scalars().all()}


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteStandaloneFeatureGuard:
    @pytest.mark.parametrize("source_type", ["FEAT", "OTHER"])
    async def test_deleting_a_feature_held_by_a_character_is_blocked(
        self, client, gm_token, player, create_class, create_character, create_feature, db_session, source_type
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        feature = await create_feature(name="Alert", source_type=source_type)
        await grant(db_session, character.id, feature.id)

        response = await client.delete(f"/features/{feature.id}", headers=auth(gm_token))

        assert response.status_code == 409
        assert (await client.get(f"/features/{feature.id}")).status_code == 200
        assert feature.id in await grants_of(db_session, character.id)

    async def test_deleting_an_unheld_feat_still_works_and_refreshes_the_cache(self, client, gm_token, create_feature):
        feature = await create_feature(name="Spare Feat", source_type="FEAT")
        assert (await client.get(f"/features/{feature.id}")).status_code == 200

        response = await client.delete(f"/features/{feature.id}", headers=auth(gm_token))

        assert response.status_code == 204
        assert (await client.get(f"/features/{feature.id}")).status_code == 404

    async def test_feat_stays_deletable_after_its_holder_loses_it(
        self, client, gm_token, player, create_class, create_character, create_feature, db_session
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        feature = await create_feature(name="Alert", source_type="FEAT")
        await grant(db_session, character.id, feature.id)
        assert (await client.delete(f"/features/{feature.id}", headers=auth(gm_token))).status_code == 409

        await revoke(db_session, character.id, feature.id)

        assert (await client.delete(f"/features/{feature.id}", headers=auth(gm_token))).status_code == 204

    async def test_unknown_feature_is_404(self, client, gm_token):
        assert (await client.delete("/features/987654", headers=auth(gm_token))).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteSourceOwnedFeatureIsOneTransaction:
    async def test_delete_revokes_auto_grants_and_refreshes_ability_scores(
        self, client, gm_token, player, create_class, create_race, create_character, db_session
    ):
        race = await create_race(name="Dwarf")
        character = await create_character(
            owner_id=player.id, class_id=(await create_class(name="Fighter")).id, race_id=race.id
        )
        created = await client.post(
            "/features",
            json={"name": "Dwarven Toughness", "source_type": "RACE", "race_id": race.id},
            headers=auth(gm_token),
        )
        feature_id = created.json()["id"]
        await client.put(
            f"/features/{feature_id}/effects",
            json={"static_groups": [{"effect_type": "ability", "items": [{"ability": "CON", "amount": 2}]}]},
            headers=auth(gm_token),
        )
        assert feature_id in await grants_of(db_session, character.id)

        response = await client.delete(f"/features/{feature_id}", headers=auth(gm_token))

        assert response.status_code == 204
        assert feature_id not in await grants_of(db_session, character.id)
        assert (await db_session.execute(select(Feature).where(Feature.id == feature_id))).scalar_one_or_none() is None

    async def test_failed_reconcile_keeps_the_feature(self, client, gm_token, create_race, create_feature, monkeypatch):
        race = await create_race(name="Dwarf")
        feature_id = (await create_feature(name="Stonecunning", source_type="RACE", race_id=race.id)).id

        async def boom(*args, **kwargs):
            raise RuntimeError("reconcile failed")

        monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", boom)

        try:
            response = await client.delete(f"/features/{feature_id}", headers=auth(gm_token))
        except RuntimeError:
            response = None  # the ASGI transport re-raises unhandled app errors
        if response is not None:
            assert response.status_code == 500

        monkeypatch.undo()
        assert (await client.get(f"/features/{feature_id}")).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdateReconcilesOnlyWhenTheLevelChanges:
    async def _class_feature_with_character(self, client, gm_token, player, create_class, create_character, level=1):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, level=5)
        created = await client.post(
            "/features",
            json={"name": "Second Wind", "source_type": "CLASS", "class_id": character_class.id, "level": level},
            headers=auth(gm_token),
        )
        assert created.status_code == 201
        return character.id, created.json()["id"]

    async def test_description_only_patch_does_not_regrant(
        self, client, gm_token, player, create_class, create_character, db_session
    ):
        character_id, feature_id = await self._class_feature_with_character(
            client, gm_token, player, create_class, create_character
        )
        assert feature_id in await grants_of(db_session, character_id)
        # remove the auto grant behind the service's back: only a reconcile would bring it back
        await revoke(db_session, character_id, feature_id)

        response = await client.patch(
            f"/features/{feature_id}", json={"description": "New text"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["description"] == "New text"
        assert feature_id not in await grants_of(db_session, character_id)

    async def test_level_patch_reconciles(self, client, gm_token, player, create_class, create_character, db_session):
        character_id, feature_id = await self._class_feature_with_character(
            client, gm_token, player, create_class, create_character
        )
        await revoke(db_session, character_id, feature_id)

        response = await client.patch(f"/features/{feature_id}", json={"level": 2}, headers=auth(gm_token))

        assert response.status_code == 200
        assert feature_id in await grants_of(db_session, character_id)

    async def test_raising_the_level_above_the_character_revokes_the_grant(
        self, client, gm_token, player, create_class, create_character, db_session
    ):
        character_id, feature_id = await self._class_feature_with_character(
            client, gm_token, player, create_class, create_character
        )

        await client.patch(f"/features/{feature_id}", json={"level": 9}, headers=auth(gm_token))

        assert feature_id not in await grants_of(db_session, character_id)

    async def test_description_patch_purges_the_holders_character_cache_only(
        self, client, gm_token, player, create_class, create_character, create_feature, db_session, monkeypatch
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        feature = await create_feature(name="Alert", source_type="FEAT")
        await grant(db_session, character.id, feature.id)
        purged = []

        async def spy(character_ids):
            purged.append(list(character_ids))

        monkeypatch.setattr("app.features.features.crud.service.invalidate_characters_cache", spy)

        response = await client.patch(
            f"/features/{feature.id}", json={"description": "Always ready"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert purged == [[character.id]]

    async def test_no_op_patch_does_not_purge_anything(
        self, client, gm_token, player, create_class, create_character, create_feature, db_session, monkeypatch
    ):
        character = await create_character(owner_id=player.id, class_id=(await create_class(name="Fighter")).id)
        feature = await create_feature(name="Alert", source_type="FEAT")
        await grant(db_session, character.id, feature.id)
        purged = []

        async def spy(character_ids):
            purged.append(list(character_ids))

        monkeypatch.setattr("app.features.features.crud.service.invalidate_characters_cache", spy)

        response = await client.patch(f"/features/{feature.id}", json={"name": "Alert"}, headers=auth(gm_token))

        assert response.status_code == 200
        assert purged == []

    async def test_patch_returns_the_loaded_effect_tree_without_a_second_fetch(
        self, client, gm_token, create_feature, create_skill
    ):
        skill = await create_skill(name="Stealth")
        feature = await create_feature(name="Sneaky", source_type="OTHER")
        await client.put(
            f"/features/{feature.id}/effects",
            json={"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
            headers=auth(gm_token),
        )

        response = await client.patch(f"/features/{feature.id}", json={"name": "Sneakier"}, headers=auth(gm_token))

        assert response.json()["static_groups"][0]["effect_type"] == "skill"
        assert "«Stealth»" in response.json()["effects_summary"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestWriteRulesAreConsistentBetweenCreateAndPatch:
    async def test_create_race_feature_with_level_zero_is_422(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            "/features",
            json={"name": "Trance", "source_type": "RACE", "race_id": race.id, "level": 0},
            headers=auth(gm_token),
        )

        assert response.status_code == 422

    async def test_patch_race_feature_level_zero_is_400(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Elf")
        feature = await create_feature(name="Trance", source_type="RACE", race_id=race.id)

        response = await client.patch(f"/features/{feature.id}", json={"level": 0}, headers=auth(gm_token))

        assert response.status_code in (400, 422)

    async def test_create_other_feature_with_feat_columns_is_422(self, client, gm_token):
        response = await client.post(
            "/features", json={"name": "Gift", "source_type": "OTHER", "min_level": 4}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_patch_other_feature_with_min_level_is_400(self, client, gm_token, create_feature):
        feature = await create_feature(name="Gift", source_type="OTHER")

        response = await client.patch(f"/features/{feature.id}", json={"min_level": 4}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_create_feat_feature_with_level_is_422(self, client, gm_token):
        response = await client.post(
            "/features", json={"name": "Alert", "source_type": "FEAT", "level": 3}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_name_over_the_column_limit_is_422_not_500(self, client, gm_token):
        response = await client.post(
            "/features", json={"name": "x" * 201, "source_type": "OTHER"}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_created_feature_is_serialized_without_refetching_the_tree(self, client, gm_token):
        response = await client.post(
            "/features", json={"name": "Fresh", "source_type": "OTHER", "description": "d"}, headers=auth(gm_token)
        )

        assert response.status_code == 201
        body = response.json()
        assert body["static_groups"] == []
        assert body["choice_groups"] == []
        assert body["effects_summary"] == ""
        assert body["has_static_effects"] is False

    async def test_feature_listing_is_stable_for_equal_names(self, client, gm_token, create_feature):
        for _ in range(5):
            await create_feature(name="Twin", source_type="OTHER")

        first = await client.get("/features", params={"size": 2, "page": 1})
        second = await client.get("/features", params={"size": 2, "page": 2})
        third = await client.get("/features", params={"size": 2, "page": 3})

        ids = [item["id"] for page in (first, second, third) for item in page.json()["items"]]
        assert len(ids) == len(set(ids)) == 5
