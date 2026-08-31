"""FastAPI dependency provider for the shared image-storage service."""

from typing import Annotated

from fastapi import Depends

from app.core.storage.service import ImageStorageService


def get_image_storage_service() -> ImageStorageService:
    """Provide the supabase-backed image storage service."""

    return ImageStorageService()


StorageServiceDep = Annotated[ImageStorageService, Depends(get_image_storage_service)]
