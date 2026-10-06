"""Fake image storage for every test here: deleting a race/subrace also removes its stored images."""

import pytest

from app import main as app_module
from app.core.storage.dependencies import get_image_storage_service


class FakeStorage:
    def __init__(self):
        self.deleted = []

    async def delete_image(self, entity: str, row_id: int) -> None:
        self.deleted.append((entity, row_id))


@pytest.fixture(autouse=True)
def storage():
    fake = FakeStorage()
    app_module.app.dependency_overrides[get_image_storage_service] = lambda: fake
    yield fake
    app_module.app.dependency_overrides.pop(get_image_storage_service, None)
