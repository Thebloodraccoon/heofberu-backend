"""Background delete guards, input validation, capability errors and choice groups."""

import pytest
from sqlalchemy import select

from app.models import Character, Feature


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteGuard:
    async def test_delete_blocked_when_feature_is_granted_to_several_characters(
        self, client, founder_token, gm_token, player, create_class, create_character, create_background, create_feature
    ):
        """Two grants of two features used to raise MultipleResultsFound (500) instead of 409."""
        background = await create_background(name="Popular")
        first = await create_feature(name="Shelter", source_type="BACKGROUND", background_id=background.id)
        second = await create_feature(name="Contacts", source_type="BACKGROUND", background_id=background.id)
        fighter = await create_class(name="Fighter")

        for feature in (first, second):
            for _ in range(2):
                character = await create_character(owner_id=player.id, class_id=fighter.id)
                added = await client.post(
                    f"/characters/{character.id}/gm-panel/features",
                    json={"feature_id": feature.id},
                    headers=auth(gm_token),
                )
                assert added.status_code == 201

        background_id = background.id
        response = await client.delete(f"/backgrounds/{background_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/backgrounds/{background_id}")).status_code == 200

    async def test_delete_with_ungranted_features_cascades_and_detaches_characters(
        self,
        client,
        founder_token,
        db_session,
        player,
        create_class,
        create_character,
        create_background,
        create_feature,
    ):
        background = await create_background(name="Doomed")
        feature = await create_feature(name="Shelter", source_type="BACKGROUND", background_id=background.id)
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, background_id=background.id)
        background_id, feature_id, character_id = background.id, feature.id, character.id

        response = await client.delete(f"/backgrounds/{background_id}", headers=auth(founder_token))

        assert response.status_code == 204
        db_session.expire_all()
        assert await db_session.get(Feature, feature_id) is None
        assert (await db_session.get(Character, character_id)).background_id is None

    async def test_delete_missing_background_returns_404(self, client, founder_token):
        response = await client.delete("/backgrounds/999999", headers=auth(founder_token))

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestValidation:
    async def test_create_rejects_blank_name(self, client, gm_token):
        response = await client.post("/backgrounds", json={"name": "   "}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_create_rejects_too_long_name(self, client, gm_token):
        response = await client.post("/backgrounds", json={"name": "x" * 101}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("gold", [-1, 2**40])
    async def test_create_rejects_out_of_range_starting_gold(self, client, gm_token, gold):
        response = await client.post(
            "/backgrounds", json={"name": "Rich", "starting_gold": gold}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_create_strips_name_whitespace(self, client, gm_token):
        response = await client.post("/backgrounds", json={"name": "  Hermit  "}, headers=auth(gm_token))

        assert response.status_code == 201
        assert response.json()["name"] == "Hermit"

    @pytest.mark.parametrize("field", ["name", "description", "starting_gold"])
    async def test_patch_rejects_explicit_null(self, client, gm_token, create_background, field):
        background = await create_background(name="Sage")

        response = await client.patch(f"/backgrounds/{background.id}", json={field: None}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_to_existing_name_returns_409(self, client, gm_token, create_background):
        await create_background(name="Acolyte")
        other = await create_background(name="Sage")

        response = await client.patch(f"/backgrounds/{other.id}", json={"name": "Acolyte"}, headers=auth(gm_token))

        assert response.status_code == 409

    async def test_patch_keeps_features_in_the_response(self, client, gm_token, create_background, create_feature):
        background = await create_background(name="Sage")
        await create_feature(name="Researcher", source_type="BACKGROUND", background_id=background.id)

        response = await client.patch(
            f"/backgrounds/{background.id}", json={"starting_gold": 10}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["starting_gold"] == 10
        assert [feature["name"] for feature in response.json()["features"]] == ["Researcher"]

    async def test_search_longer_than_limit_returns_422(self, client):
        response = await client.get("/backgrounds", params={"search": "x" * 101})

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestGetById:
    async def test_get_returns_features_skills_items_and_suggestions(
        self, client, gm_token, create_background, create_feature, create_skill, create_item
    ):
        background = await create_background(name="Sage")
        await create_feature(name="Researcher", source_type="BACKGROUND", background_id=background.id)
        skill = await create_skill(name="Arcana", ability="INT")
        item = await create_item(name="Ink", item_type="ADVENTURING_GEAR")
        await client.put(f"/backgrounds/{background.id}/skills", json={"skill_ids": [skill.id]}, headers=auth(gm_token))
        await client.put(
            f"/backgrounds/{background.id}/items",
            json={"items": [{"item_id": item.id, "quantity": 2}]},
            headers=auth(gm_token),
        )

        body = (await client.get(f"/backgrounds/{background.id}")).json()

        assert [feature["name"] for feature in body["features"]] == ["Researcher"]
        assert [entry["id"] for entry in body["granted_skills"]] == [skill.id]
        assert [(entry["item_id"], entry["quantity"]) for entry in body["starting_items"]] == [(item.id, 2)]
        assert len(body["suggestions"]) == 4
        assert (await client.get(f"/backgrounds/{background.id}/features")).json() == body["features"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestCapabilityErrors:
    async def test_set_skills_with_unknown_skill_returns_400(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/skills", json={"skill_ids": [9999]}, headers=auth(gm_token)
        )

        assert response.status_code == 400

    async def test_set_skills_with_duplicates_returns_422(self, client, gm_token, create_background, create_skill):
        background = await create_background(name="Sage")
        skill = await create_skill(name="Arcana", ability="INT")

        response = await client.put(
            f"/backgrounds/{background.id}/skills", json={"skill_ids": [skill.id, skill.id]}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_set_skills_with_out_of_range_id_returns_422(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/skills", json={"skill_ids": [2**40]}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_set_skills_for_missing_background_returns_404(self, client, gm_token):
        response = await client.put("/backgrounds/999999/skills", json={"skill_ids": []}, headers=auth(gm_token))

        assert response.status_code == 404

    async def test_set_skills_empty_list_clears(self, client, gm_token, create_background, create_skill):
        background = await create_background(name="Sage")
        skill = await create_skill(name="Arcana", ability="INT")
        await client.put(f"/backgrounds/{background.id}/skills", json={"skill_ids": [skill.id]}, headers=auth(gm_token))

        response = await client.put(
            f"/backgrounds/{background.id}/skills", json={"skill_ids": []}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["granted_skills"] == []

    async def test_set_tags_with_unknown_tag_returns_400(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/tags", json={"tag_ids": [9999]}, headers=auth(gm_token)
        )

        assert response.status_code == 400

    async def test_set_tags_for_missing_background_returns_404(self, client, gm_token):
        response = await client.put("/backgrounds/999999/tags", json={"tag_ids": []}, headers=auth(gm_token))

        assert response.status_code == 404

    @pytest.mark.parametrize("path", ["items", "features", "suggestions", "choice-groups"])
    async def test_reads_for_missing_background_return_404(self, client, path):
        assert (await client.get(f"/backgrounds/999999/{path}")).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroups:
    async def test_new_background_has_no_choice_groups(self, client, create_background):
        background = await create_background(name="Sage")

        response = await client.get(f"/backgrounds/{background.id}/choice-groups")

        assert response.status_code == 200
        assert response.json()["choice_groups"] == []

    async def test_gm_can_replace_choice_groups(self, client, gm_token, create_background, create_item):
        background = await create_background(name="Sage")
        quill = await create_item(name="Quill", item_type="ADVENTURING_GEAR")
        ink = await create_item(name="Ink", item_type="ADVENTURING_GEAR")

        response = await client.put(
            f"/backgrounds/{background.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "options": [{"item_id": quill.id, "quantity": 1}, {"item_id": ink.id, "quantity": 1}],
                    }
                ]
            },
            headers=auth(gm_token),
        )

        assert response.status_code == 200
        groups = response.json()["choice_groups"]
        assert len(groups) == 1
        assert {option["item_id"] for option in groups[0]["options"]} == {quill.id, ink.id}

        detail = (await client.get(f"/backgrounds/{background.id}")).json()
        assert len(detail["starting_choice_groups"]) == 1

        cleared = await client.put(
            f"/backgrounds/{background.id}/choice-groups", json={"choice_groups": []}, headers=auth(gm_token)
        )
        assert cleared.json()["choice_groups"] == []

    async def test_unknown_item_returns_400(self, client, gm_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/choice-groups",
            json={"choice_groups": [{"pick_count": 1, "options": [{"item_id": 9999, "quantity": 1}]}]},
            headers=auth(gm_token),
        )

        assert response.status_code == 400

    async def test_player_cannot_replace_choice_groups(self, client, player_token, create_background):
        background = await create_background(name="Sage")

        response = await client.put(
            f"/backgrounds/{background.id}/choice-groups", json={"choice_groups": []}, headers=auth(player_token)
        )

        assert response.status_code == 403

    async def test_missing_background_returns_404(self, client, gm_token):
        response = await client.put(
            "/backgrounds/999999/choice-groups", json={"choice_groups": []}, headers=auth(gm_token)
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSuggestionLastOfTypeGuard:
    async def test_cannot_delete_the_last_suggestion_of_a_type(self, client, gm_token, create_background):
        background_id = (await create_background(name="Sage")).id
        suggestions = (await client.get(f"/backgrounds/{background_id}/suggestions")).json()

        response = await client.delete(
            f"/backgrounds/{background_id}/suggestions/{suggestions[0]['id']}", headers=auth(gm_token)
        )

        assert response.status_code == 409
        assert len((await client.get(f"/backgrounds/{background_id}/suggestions")).json()) == 4

    async def test_cannot_retype_the_last_suggestion_of_a_type(self, client, gm_token, create_background):
        background = await create_background(name="Sage")
        suggestions = (await client.get(f"/backgrounds/{background.id}/suggestions")).json()
        bond = next(entry for entry in suggestions if entry["suggestion_type"] == "BOND")

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{bond['id']}",
            json={"suggestion_type": "FLAW"},
            headers=auth(gm_token),
        )

        assert response.status_code == 409

    async def test_can_delete_and_retype_once_a_type_has_spares(self, client, gm_token, create_background):
        background = await create_background(name="Sage")
        base = f"/backgrounds/{background.id}/suggestions"
        extra = await client.post(
            base, json={"suggestion_type": "BOND", "text": "Second bond."}, headers=auth(gm_token)
        )
        extra_id = extra.json()["id"]

        retyped = await client.patch(f"{base}/{extra_id}", json={"suggestion_type": "IDEAL"}, headers=auth(gm_token))
        assert retyped.status_code == 200
        assert retyped.json()["suggestion_type"] == "IDEAL"

        deleted = await client.delete(f"{base}/{extra_id}", headers=auth(gm_token))
        assert deleted.status_code == 204

    @pytest.mark.parametrize("payload", [{"text": None}, {"suggestion_type": None}])
    async def test_patch_rejects_explicit_null(self, client, gm_token, create_background, payload):
        background = await create_background(name="Sage")
        suggestion_id = (await client.get(f"/backgrounds/{background.id}/suggestions")).json()[0]["id"]

        response = await client.patch(
            f"/backgrounds/{background.id}/suggestions/{suggestion_id}", json=payload, headers=auth(gm_token)
        )

        assert response.status_code == 422

    async def test_delete_cascade_survives_with_unrelated_rows(
        self, client, founder_token, db_session, create_background
    ):
        background = await create_background(name="Sage")

        response = await client.delete(f"/backgrounds/{background.id}", headers=auth(founder_token))

        assert response.status_code == 204
        remaining = await db_session.execute(select(Feature.id).where(Feature.background_id == background.id))
        assert remaining.all() == []
