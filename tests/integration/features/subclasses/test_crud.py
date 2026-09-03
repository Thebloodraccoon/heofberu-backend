"""Tests for the subclass endpoints: CRUD and delete guards."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubclassCrud:
    async def test_player_cannot_create_subclass(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/subclasses",
            json={"name": "Champion", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_subclass(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/subclasses",
            json={"name": "Champion", "class_id": character_class.id, "description": "A master of combat."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Champion"
        assert body["class_id"] == character_class.id

    async def test_create_subclass_for_missing_class_returns_404(self, client, gm_token):
        response = await client.post(
            "/subclasses",
            json={"name": "Champion", "class_id": 9999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_create_duplicate_subclass_name_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        await client.post(
            "/subclasses",
            json={"name": "Champion", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        response = await client.post(
            "/subclasses",
            json={"name": "Champion", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_list_subclasses_for_class(self, client, create_class, create_subclass):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        await create_subclass(class_id=fighter.id, name="Champion")
        await create_subclass(class_id=fighter.id, name="Battle Master")
        await create_subclass(class_id=rogue.id, name="Assassin")

        response = await client.get("/subclasses", params={"class_id": fighter.id})

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Battle Master", "Champion"]

    async def test_get_subclass(self, client, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.get(f"/subclasses/{subclass.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Champion"

    async def test_get_missing_subclass_returns_404(self, client):
        assert (await client.get("/subclasses/9999")).status_code == 404

    async def test_gm_can_update_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.patch(
            f"/subclasses/{subclass.id}",
            json={"name": "Battle Master"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Battle Master"

    async def test_player_cannot_update_subclass(self, client, player_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.patch(
            f"/subclasses/{subclass.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_cannot_delete_subclass(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Doomed")

        response = await client.delete(f"/subclasses/{subclass.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/subclasses/{subclass.id}")).status_code == 200

    async def test_founder_can_delete_subclass(self, client, founder_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Doomed")

        response = await client.delete(
            f"/subclasses/{subclass.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 204
        assert (await client.get(f"/subclasses/{subclass.id}")).status_code == 404

    async def test_delete_subclass_in_use_returns_409(self, client, founder_token, create_class, create_subclass, create_user, create_character):
        player = await create_user()
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="In Use")
        await create_character(owner_id=player.id, class_id=character_class.id, subclass_id=subclass.id)

        response = await client.delete(
            f"/subclasses/{subclass.id}", headers={"Authorization": f"Bearer {founder_token}"}
        )

        assert response.status_code == 409
        assert (await client.get(f"/subclasses/{subclass.id}")).status_code == 200
