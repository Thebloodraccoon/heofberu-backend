"""
Integration tests for article gallery image upload/list/delete with a mocked storage service.

The real ``ImageStorageService`` talks to Supabase Storage, unavailable in the test
environment — see ``tests/integration/features/races/test_image.py`` for the same pattern.
"""

import pytest

from app import main as app_module
from app.core.storage.dependencies import get_image_storage_service


class FakeImageStorage:
    """In-process stub replacing Supabase-backed storage for tests."""

    def __init__(self):
        self.uploaded = []
        self.deleted = []

    async def upload_image(self, entity: str, row_id: int, content: bytes, content_type: str) -> str:
        self.uploaded.append((entity, row_id, content_type))
        return f"https://fake-storage/{entity}/{row_id}.png"

    async def delete_image(self, entity: str, row_id: int) -> None:
        self.deleted.append((entity, row_id))


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleImages:
    @pytest.fixture(autouse=True)
    def _fake_storage(self):
        fake = FakeImageStorage()
        app_module.app.dependency_overrides[get_image_storage_service] = lambda: fake
        yield fake
        app_module.app.dependency_overrides.pop(get_image_storage_service, None)

    def _png_files(self):
        return {"image": ("map.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "image/png")}

    async def test_player_cannot_upload_image(self, client, create_article, player_token, _fake_storage):
        article = await create_article(title="Khazad-dum")

        response = await client.post(
            f"/articles/{article['id']}/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.uploaded == []

    async def test_gm_can_upload_image(self, client, create_article, gm_token, _fake_storage):
        article = await create_article(title="Khazad-dum")

        response = await client.post(
            f"/articles/{article['id']}/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["article_id"] == article["id"]
        assert body["image_url"]
        assert _fake_storage.uploaded == [(f"articles/{article['id']}", body["id"], "image/png")]

    async def test_upload_for_missing_article_returns_404(self, client, gm_token, _fake_storage):
        response = await client.post(
            "/articles/999999/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_list_images(self, client, create_article, player_token, _fake_storage):
        article = await create_article(title="Khazad-dum")

        response = await client.get(
            f"/articles/{article['id']}/images",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_list_uploaded_images(self, client, create_article, gm_token, _fake_storage):
        article = await create_article(title="Khazad-dum")
        headers = {"Authorization": f"Bearer {gm_token}"}
        uploaded = await client.post(f"/articles/{article['id']}/images", files=self._png_files(), headers=headers)

        response = await client.get(f"/articles/{article['id']}/images", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert [img["id"] for img in body] == [uploaded.json()["id"]]

    async def test_gm_can_delete_image(self, client, create_article, gm_token, _fake_storage):
        article = await create_article(title="Khazad-dum")
        headers = {"Authorization": f"Bearer {gm_token}"}
        uploaded = (
            await client.post(f"/articles/{article['id']}/images", files=self._png_files(), headers=headers)
        ).json()

        response = await client.delete(f"/articles/{article['id']}/images/{uploaded['id']}", headers=headers)

        assert response.status_code == 204
        assert _fake_storage.deleted == [(f"articles/{article['id']}", uploaded["id"])]

        listed = await client.get(f"/articles/{article['id']}/images", headers=headers)
        assert listed.json() == []

    async def test_player_cannot_delete_image(self, client, create_article, gm_token, player_token, _fake_storage):
        article = await create_article(title="Khazad-dum")
        uploaded = (
            await client.post(
                f"/articles/{article['id']}/images",
                files=self._png_files(),
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()

        response = await client.delete(
            f"/articles/{article['id']}/images/{uploaded['id']}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.deleted == []

    async def test_delete_missing_image_returns_404(self, client, create_article, gm_token, _fake_storage):
        article = await create_article(title="Khazad-dum")

        response = await client.delete(
            f"/articles/{article['id']}/images/999999",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
