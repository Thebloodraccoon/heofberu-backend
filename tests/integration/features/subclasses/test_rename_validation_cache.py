"""Subclass writes: class-scoped rename conflicts, 422 validation, full responses, listing and cache freshness."""

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubclassRename:
    async def test_rename_to_a_name_used_in_another_class_is_allowed(
        self, client, gm_token, create_class, create_subclass
    ):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        await create_subclass(class_id=rogue.id, name="Assassin")
        mine = await create_subclass(class_id=fighter.id, name="Champion")

        response = await client.patch(f"/subclasses/{mine.id}", json={"name": "Assassin"}, headers=auth(gm_token))

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Assassin"
        assert response.json()["class_id"] == fighter.id

    async def test_rename_to_a_sibling_name_returns_400(self, client, gm_token, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        await create_subclass(class_id=fighter.id, name="Champion")
        other = await create_subclass(class_id=fighter.id, name="Battle Master")

        response = await client.patch(f"/subclasses/{other.id}", json={"name": "Champion"}, headers=auth(gm_token))

        assert response.status_code == 400
        assert (await client.get(f"/subclasses/{other.id}")).json()["name"] == "Battle Master"

    async def test_patch_keeping_its_own_name_is_not_a_conflict(self, client, gm_token, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=fighter.id, name="Champion")

        response = await client.patch(
            f"/subclasses/{subclass.id}", json={"name": "Champion", "description": "d"}, headers=auth(gm_token)
        )

        assert response.status_code == 200

    async def test_same_name_may_exist_in_two_classes_on_create(self, client, gm_token, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        await create_subclass(class_id=rogue.id, name="Assassin")

        response = await client.post(
            "/subclasses", json={"name": "Assassin", "class_id": fighter.id}, headers=auth(gm_token)
        )

        assert response.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubclassValidation:
    @pytest.mark.parametrize(
        "extra",
        [{"name": ""}, {"name": "x" * 101}, {"image_url": "javascript:alert(1)"}, {"description": "x" * 10_001}],
    )
    async def test_invalid_create_returns_422(self, client, gm_token, create_class, extra):
        fighter = await create_class(name="Fighter")

        response = await client.post(
            "/subclasses", json={"name": "Champion", "class_id": fighter.id, **extra}, headers=auth(gm_token)
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("payload", [{"name": None}, {"description": None}, {"name": ""}, {"name": "x" * 101}])
    async def test_invalid_patch_returns_422(self, client, gm_token, create_class, create_subclass, payload):
        fighter = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=fighter.id, name="Champion")

        response = await client.patch(f"/subclasses/{subclass.id}", json=payload, headers=auth(gm_token))

        assert response.status_code == 422
        assert (await client.get(f"/subclasses/{subclass.id}")).json()["name"] == "Champion"

    async def test_class_id_cannot_be_changed_through_patch(self, client, gm_token, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        subclass = await create_subclass(class_id=fighter.id, name="Champion")

        response = await client.patch(
            f"/subclasses/{subclass.id}", json={"class_id": rogue.id, "description": "d"}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["class_id"] == fighter.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubclassResponsesAndListing:
    async def test_patch_response_carries_the_subclass_features(
        self, client, gm_token, create_class, create_subclass, create_feature
    ):
        fighter = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=fighter.id, name="Champion")
        await create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=3)

        patched = await client.patch(f"/subclasses/{subclass.id}", json={"description": "d"}, headers=auth(gm_token))

        assert [f["name"] for f in patched.json()["features"]] == ["Improved Critical"]
        assert patched.json() == (await client.get(f"/subclasses/{subclass.id}")).json()

    async def test_list_for_unknown_class_returns_404(self, client):
        assert (await client.get("/subclasses", params={"class_id": 999999})).status_code == 404

    async def test_list_without_filter_returns_all_subclasses(self, client, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        await create_subclass(class_id=fighter.id, name="Champion")
        await create_subclass(class_id=rogue.id, name="Assassin")

        response = await client.get("/subclasses")

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Assassin", "Champion"]

    async def test_listing_and_detail_are_fresh_after_writes(
        self, caching_on, client, gm_token, founder_token, create_class
    ):
        fighter = await create_class(name="Fighter")
        listing = {"class_id": fighter.id}
        assert (await client.get("/subclasses", params=listing)).json() == []

        created = await client.post(
            "/subclasses", json={"name": "Champion", "class_id": fighter.id}, headers=auth(gm_token)
        )
        subclass_id = created.json()["id"]
        assert [s["name"] for s in (await client.get("/subclasses", params=listing)).json()] == ["Champion"]

        await client.patch(f"/subclasses/{subclass_id}", json={"name": "Battle Master"}, headers=auth(gm_token))
        assert [s["name"] for s in (await client.get("/subclasses", params=listing)).json()] == ["Battle Master"]

        assert (await client.delete(f"/subclasses/{subclass_id}", headers=auth(founder_token))).status_code == 204
        assert (await client.get("/subclasses", params=listing)).json() == []
        assert (await client.get(f"/subclasses/{subclass_id}")).status_code == 404

    async def test_deleting_a_subclass_drops_its_cached_feature_list(
        self, caching_on, client, founder_token, create_class, create_subclass, create_feature
    ):
        fighter = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=fighter.id, name="Champion")
        await create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=3)
        features_path = f"/subclasses/{subclass.id}/features"
        assert len((await client.get(features_path)).json()) == 1

        assert (await client.delete(f"/subclasses/{subclass.id}", headers=auth(founder_token))).status_code == 204

        assert (await client.get(features_path)).status_code == 404
