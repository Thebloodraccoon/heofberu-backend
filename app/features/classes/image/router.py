"""Class image endpoints: upload and delete a class's catalog image."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.features.classes.dependencies import ClassImageDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{class_id:int}/image",
    response_model=dict[str, str],
    summary="Upload a class's image",
    responses={
        400: {"description": "Invalid or oversized image, or the upload failed."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def upload_class_image(
    class_id: int,
    image_service: ClassImageDep,
    _: GmUserDep,
    image: Annotated[UploadFile, File(description="Image file (JPEG, PNG, WebP or GIF, max 5 MB).")],
):
    """
    Upload (or replace) the class's catalog image and return its public URL.
    **GM only.**
    """

    content = await image.read()
    try:
        url = await image_service.upload_image(
            class_id,
            content,
            image.content_type or "",
        )
    finally:
        await image.close()

    return {"image_url": url}


@router.delete(
    "/{class_id:int}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a class's image",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def delete_class_image(
    class_id: int,
    image_service: ClassImageDep,
    _: GmUserDep,
):
    """Remove the class's image from storage and clear its ``image_url``. **GM only.**"""

    await image_service.delete_image(class_id)
    return None
