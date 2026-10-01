"""FastAPI dependency provider for the shared image-storage service."""

from typing import Annotated

from fastapi import BackgroundTasks, Depends

from app.core.storage.service import ImageStorageService


def get_image_storage_service(background_tasks: BackgroundTasks) -> ImageStorageService:
    """Provide the supabase-backed image storage service; its deletes run after the response."""

    return ImageStorageService(background_tasks)


StorageServiceDep = Annotated[ImageStorageService, Depends(get_image_storage_service)]
