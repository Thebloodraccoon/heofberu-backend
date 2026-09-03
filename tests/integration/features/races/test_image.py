"""Integration tests for catalog image upload/delete with a mocked storage service.

The real ``ImageStorageService`` talks to Supabase Storage, which is not
available in the test environment. We override the ``get_image_storage_service``
dependency with the in-memory :class:`FakeImageStorage` below, leaving the
router wiring, authorization, and the per-capability image services exercised
end-to-end while the image format/size validation is covered by the unit tests
in ``tests/unit/core/test_image_validation.py``.
"""

import pytest

from app import main as app_module
from app.core.storage.dependencies import get_image_storage_service


class FakeImageStorage:
    """In-process stub replacing Supabase-backed storage for tests."""

    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def reset(self):
        self.uploaded = []
        self.deleted = []

    async def upload_image(self, entity: str, row_id: int, content: bytes, content_type: str) -> str:
        self.uploaded.append((entity, row_id, content_type))
        return f"https://fake-storage/{entity}/{row_id}.png"

    async def delete_image(self, entity: str, row_id: int) -> None:
        self.deleted.append((entity, row_id))


@pytest.mark.integration
@pytest.mark.asyncio
class TestImageUploadDelete:
    @pytest.fixture(autouse=True)
    def _fake_storage(self):
        fake = FakeImageStorage()
        app_module.app.dependency_overrides[get_image_storage_service] = lambda: fake
        yield fake
        app_module.app.dependency_overrides.pop(get_image_storage_service, None)

    def _png_files(self):
        return {"image": ("elf.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "image/png")}

    async def test_player_cannot_upload_race_image(self, client, player_token, create_race, _fake_storage):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.uploaded == []

    async def test_gm_can_upload_and_store_url(self, client, gm_token, create_race, _fake_storage):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert "image_url" in response.json()

        fetched = await client.get(f"/races/{race.id}")
        assert fetched.json()["image_url"] == response.json()["image_url"]

    async def test_upload_for_missing_race_returns_404(self, client, gm_token, _fake_storage):
        response = await client.put(
            "/races/99999/image",
            files=self._png_files(),
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_gm_can_delete_race_image(self, client, gm_token, create_race, _fake_storage):
        race = await create_race(name="Elf")

        response = await client.delete(
            f"/races/{race.id}/image",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204

        fetched = await client.get(f"/races/{race.id}")
        assert fetched.json()["image_url"] is None

    async def test_player_cannot_delete_race_image(self, client, player_token, create_race, _fake_storage):
        race = await create_race(name="Elf")

        response = await client.delete(
            f"/races/{race.id}/image",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
        assert _fake_storage.deleted == []
