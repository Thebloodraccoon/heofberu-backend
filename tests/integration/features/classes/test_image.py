"""
Integration tests for class catalog image upload/delete with a mocked storage service.

See ``tests/integration/features/races/test_image.py`` for the pattern this
mirrors — the real ``ImageStorageService`` talks to Supabase Storage, which
is not available in the test environment.
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
class TestClassImageUploadDelete:
    @pytest.fixture(autouse=True)
    def _fake_storage(self):
        fake = FakeImageStorage()
        app_module.app.dependency_overrides[get_image_storage_service] = lambda: fake
        yield fake
        app_module.app.dependency_overrides.pop(get_image_storage_service, None)

    def _png_files(self):
        return {"image": ("fighter.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "image/png")}

    async def test_player_cannot_upload_class_image(self, client, player_token, create_class, _fake_storage):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            f"/classes/{character_class.id}/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.uploaded == []

    async def test_gm_can_upload_and_store_url(self, client, gm_token, create_class, _fake_storage):
        character_class = await create_class(name="Fighter")

        response = await client.put(
            f"/classes/{character_class.id}/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert "image_url" in response.json()
        assert _fake_storage.uploaded == [("classes", character_class.id, "image/png")]

        fetched = await client.get(f"/classes/{character_class.id}")
        assert fetched.json()["image_url"] == response.json()["image_url"]

    async def test_upload_for_missing_class_returns_404(self, client, gm_token, _fake_storage):
        response = await client.put(
            "/classes/99999/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_gm_can_delete_class_image(self, client, gm_token, create_class, _fake_storage):
        character_class = await create_class(name="Fighter")

        response = await client.delete(
            f"/classes/{character_class.id}/image",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert _fake_storage.deleted == [("classes", character_class.id)]

        fetched = await client.get(f"/classes/{character_class.id}")
        assert fetched.json()["image_url"] is None

    async def test_delete_for_missing_class_returns_404(self, client, gm_token, _fake_storage):
        response = await client.delete(
            "/classes/99999/image",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_delete_class_image(self, client, player_token, create_class, _fake_storage):
        character_class = await create_class(name="Fighter")

        response = await client.delete(
            f"/classes/{character_class.id}/image",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.deleted == []
