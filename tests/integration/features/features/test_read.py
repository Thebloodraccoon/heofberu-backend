"""Tests for the feature read endpoints."""

import pytest


@pytest.mark.integration
class TestFeatureOpenRead:
    def test_list_features(self, client, create_feature):
        create_feature(name="Extra Attack", source_type="OTHER")
        create_feature(name="Darkvision", source_type="OTHER")

        response = client.get("/features/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Extra Attack", "Darkvision"} <= names

    def test_list_features_filters_by_source_type(self, client, create_class, create_feature):
        character_class = create_class(name="Fighter")
        create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)

        response = client.get(f"/features/?source_type=CLASS&class_id={character_class.id}")

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Extra Attack"]

    def test_list_features_filters_by_subclass_id(self, client, create_class, create_subclass, create_feature):
        character_class = create_class(name="Fighter")
        subclass = create_subclass(class_id=character_class.id, name="Champion")
        create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=3)

        response = client.get(f"/features/?source_type=SUBCLASS&subclass_id={subclass.id}")

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Improved Critical"]

    def test_get_feature_by_id(self, client, create_feature):
        feature = create_feature(name="Extra Attack", source_type="OTHER")

        response = client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Extra Attack"

    def test_get_feature_404(self, client):
        assert client.get("/features/999999").status_code == 404
