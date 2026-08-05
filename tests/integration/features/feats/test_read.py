"""Tests for the feat read endpoints."""

import pytest


@pytest.mark.integration
class TestFeatOpenRead:
    def test_list_feats(self, client, create_feat):
        create_feat(name="Alert")
        create_feat(name="Lucky")

        response = client.get("/feats/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Alert", "Lucky"} <= names

    def test_get_feat_by_id(self, client, create_feat):
        feat = create_feat(name="Alert")

        response = client.get(f"/feats/{feat.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Alert"

    def test_get_feat_404(self, client):
        assert client.get("/feats/999999").status_code == 404
