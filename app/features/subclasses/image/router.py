"""Subclass image endpoints: upload and delete a subclass's catalog image."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.features.subclasses.dependencies import SubclassImageDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{subclass_id:int}/image",
    response_model=dict[str, str],
    summary="Upload a subclass's image",
    responses={
        400: {"description": "Invalid or oversized image, or the upload failed."},
        404: {"description": "No subclass exists with the given ID."},
    },
)
async def upload_subclass_image(
    subclass_id: int,
    image_service: SubclassImageDep,
    _: GmUserDep,
    image: Annotated[UploadFile, File(description="Image file (JPEG, PNG, WebP or GIF, max 5 MB).")],
):
    """
    Upload (or replace) the subclass's catalog image and return its public URL.
    **GM only.**
    """

    content = await image.read()
    try:
        url = await image_service.upload_image(
            subclass_id,
            content,
            image.content_type or "",
        )
    finally:
        await image.close()

    return {"image_url": url}


@router.delete(
    "/{subclass_id:int}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subclass's image",
    responses={404: {"description": "No subclass exists with the given ID."}},
)
async def delete_subclass_image(
    subclass_id: int,
    image_service: SubclassImageDep,
    _: GmUserDep,
):
    """Remove the subclass's image from storage and clear its ``image_url``. **GM only.**"""

    await image_service.delete_image(subclass_id)
    return None
