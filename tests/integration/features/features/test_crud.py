"""Tests for the feature write endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureCrud:
    async def test_player_cannot_create_feature(self, client, player_token):
        response = await client.post(
            "/features",
            json={"name": "Custom Feature", "source_type": "OTHER"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_other_feature(self, client, gm_token):
        response = await client.post(
            "/features",
            json={"name": "Custom Feature", "source_type": "OTHER"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Custom Feature"
        assert response.json()["source_type"] == "OTHER"

    async def test_cannot_create_class_feature_directly(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/features",
            json={"name": "Extra Attack", "source_type": "CLASS", "class_id": character_class.id, "level": 5},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_cannot_create_subclass_feature_directly(self, client, gm_token, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.post(
            "/features",
            json={"name": "Improved Critical", "source_type": "SUBCLASS", "subclass_id": subclass.id, "level": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "source_type,fk_name",
        [
            ("RACE", "race_id"),
            ("SUBRACE", "subrace_id"),
            ("BACKGROUND", "background_id"),
        ],
    )
    async def test_cannot_create_source_owned_feature_directly(
        self, client, gm_token, create_race, create_subrace, create_background, create_feat, source_type, fk_name
    ):
        elf = await create_race(name="Elf")
        parent_by_type = {
            "RACE": elf,
            "SUBRACE": await create_subrace(race_id=elf.id),
            "BACKGROUND": await create_background(name="Acolyte"),
        }
        parent = parent_by_type[source_type]

        response = await client.post(
            "/features",
            json={"name": "Owned Feature", "source_type": source_type, fk_name: parent.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_other_feature_cannot_set_source_fk(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/features",
            json={"name": "Bad Feature", "source_type": "OTHER", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_create_feature_with_mismatched_fk_returns_422(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            "/features",
            json={"name": "Bad Feature", "source_type": "CLASS", "race_id": race.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_gm_can_update_feature(self, client, gm_token, create_feature):
        feature = await create_feature(name="Old Feature", source_type="OTHER")

        response = await client.patch(
            f"/features/{feature.id}",
            json={"name": "New Feature"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Feature"

    async def test_cannot_update_feature_source(self, client, gm_token, create_feature):
        feature = await create_feature(name="Old Feature", source_type="OTHER")

        response = await client.patch(
            f"/features/{feature.id}",
            json={"source_type": "RACE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_gm_can_set_level_on_other_feature(self, client, gm_token, create_feature):
        feature = await create_feature(name="Old Feature", source_type="OTHER")

        response = await client.patch(
            f"/features/{feature.id}",
            json={"level": 5},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["level"] == 5

    async def test_gm_can_delete_feature(self, client, gm_token, create_feature):
        feature = await create_feature(name="Doomed Feature", source_type="OTHER")

        response = await client.delete(f"/features/{feature.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/features/{feature.id}")).status_code == 404

    async def test_cannot_update_source_owned_feature_via_features_crud(
        self, client, gm_token, create_class, create_feature
    ):
        character_class = await create_class(name="Fighter")
        feature = await create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)

        response = await client.patch(
            f"/features/{feature.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert (await client.get(f"/features/{feature.id}")).status_code == 404
        fetched = await client.get(f"/classes/{character_class.id}/features")
        assert [item["name"] for item in fetched.json()] == ["Extra Attack"]

    async def test_cannot_delete_source_owned_feature_via_features_crud(
        self, client, gm_token, create_race, create_feature
    ):
        race = await create_race(name="Elf")
        feature = await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)

        response = await client.delete(f"/features/{feature.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 400
        assert (await client.get(f"/features/{feature.id}")).status_code == 404
        fetched = await client.get(f"/races/{race.id}/features")
        assert [item["name"] for item in fetched.json()] == ["Darkvision"]
