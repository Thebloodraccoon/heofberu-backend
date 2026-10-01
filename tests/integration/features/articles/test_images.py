"""
Integration tests for article gallery image upload/list/delete with a mocked storage service.

The real ``ImageStorageService`` talks to Supabase Storage, unavailable in the test
environment — see ``tests/integration/features/races/test_image.py`` for the same pattern.
"""

import pytest
from sqlalchemy import text

from app import main as app_module
from app.core.storage.dependencies import get_image_storage_service
from app.core.storage.service import ImageUploadError


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
        [(entity, row_id, content_type)] = _fake_storage.uploaded
        assert (row_id, content_type) == (body["id"], "image/png")
        prefix, storage_key = entity.rsplit("/", 1)
        assert prefix == f"articles/{article['id']}"
        assert len(storage_key) == 36  # uuid4: the public URL can't be guessed from the ids

    async def test_failed_upload_still_removes_storage_object(self, client, create_article, gm_token, _fake_storage):
        article = await create_article(title="Khazad-dum")
        headers = {"Authorization": f"Bearer {gm_token}"}

        async def failing_upload(entity, row_id, content, content_type):
            _fake_storage.uploaded.append((entity, row_id, content_type))
            raise ImageUploadError("timed out after the object was written")

        _fake_storage.upload_image = failing_upload

        response = await client.post(f"/articles/{article['id']}/images", files=self._png_files(), headers=headers)

        assert response.status_code == 400
        [(entity, row_id, _)] = _fake_storage.uploaded
        assert _fake_storage.deleted == [(entity, row_id)]
        listed = await client.get(f"/articles/{article['id']}/images", headers=headers)
        assert listed.json() == []

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
        [uploaded_entity] = [entity for entity, row_id, _ in _fake_storage.uploaded if row_id == uploaded["id"]]
        assert _fake_storage.deleted == [(uploaded_entity, uploaded["id"])]

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


@pytest.mark.integration
@pytest.mark.asyncio
class TestArticleImageTransactions:
    @pytest.fixture(autouse=True)
    def _fake_storage(self):
        fake = FakeImageStorage()
        app_module.app.dependency_overrides[get_image_storage_service] = lambda: fake
        yield fake
        app_module.app.dependency_overrides.pop(get_image_storage_service, None)

    def _png_files(self):
        return {"image": ("map.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "image/png")}

    async def test_no_db_transaction_is_open_during_the_network_upload(
        self, client, create_article, gm_token, db_session, _fake_storage
    ):
        article = await create_article(title="Khazad-dum")
        seen = []

        async def upload(entity, row_id, content, content_type):
            seen.append(db_session.in_transaction())
            return f"https://fake-storage/{entity}/{row_id}.png"

        _fake_storage.upload_image = upload

        response = await client.post(
            f"/articles/{article['id']}/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert seen == [False]

    async def test_failed_upload_leaves_no_row_and_cleans_storage(
        self, client, create_article, gm_token, db_session, _fake_storage
    ):
        article = await create_article(title="Khazad-dum")

        async def failing(entity, row_id, content, content_type):
            raise ImageUploadError("boom")

        _fake_storage.upload_image = failing

        response = await client.post(
            f"/articles/{article['id']}/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert len(_fake_storage.deleted) == 1
        count = await db_session.scalar(text("SELECT count(*) FROM article_images"))
        assert count == 0

    async def test_article_deleted_during_upload_cleans_storage_and_returns_404(
        self, client, create_article, gm_token, db_session, _fake_storage
    ):
        article = await create_article(title="Khazad-dum")

        async def upload_then_article_vanishes(entity, row_id, content, content_type):
            await db_session.execute(text("DELETE FROM articles WHERE id = :id"), {"id": article["id"]})
            await db_session.commit()
            return "https://fake-storage/x.png"

        _fake_storage.upload_image = upload_then_article_vanishes

        response = await client.post(
            f"/articles/{article['id']}/images",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
        assert len(_fake_storage.deleted) == 1

    async def test_image_limit_per_article(self, client, create_article, gm_token, monkeypatch, _fake_storage):
        monkeypatch.setattr("app.features.articles.images.service.MAX_IMAGES_PER_ARTICLE", 1)
        article = await create_article(title="Khazad-dum")
        headers = {"Authorization": f"Bearer {gm_token}"}

        first = await client.post(f"/articles/{article['id']}/images", files=self._png_files(), headers=headers)
        second = await client.post(f"/articles/{article['id']}/images", files=self._png_files(), headers=headers)

        assert (first.status_code, second.status_code) == (201, 400)
        assert len(_fake_storage.uploaded) == 1
