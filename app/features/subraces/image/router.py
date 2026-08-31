"""Subrace image endpoints: upload and delete a subrace's catalog image."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.features.subraces.dependencies import SubraceImageDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{subrace_id:int}/image",
    response_model=dict[str, str],
    summary="Upload a subrace's image",
    responses={
        400: {"description": "Invalid or oversized image, or the upload failed."},
        404: {"description": "No subrace exists with the given ID."},
    },
)
async def upload_subrace_image(
    subrace_id: int,
    image_service: SubraceImageDep,
    _: GmUserDep,
    image: Annotated[UploadFile, File(description="Image file (JPEG, PNG, WebP or GIF, max 5 MB).")],
):
    """
    Upload (or replace) the subrace's catalog image and return its public URL.
    **GM only.**
    """

    content = await image.read()
    try:
        url = await image_service.upload_image(
            subrace_id,
            content,
            image.content_type or "",
        )
    finally:
        await image.close()

    return {"image_url": url}


@router.delete(
    "/{subrace_id:int}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subrace's image",
    responses={404: {"description": "No subrace exists with the given ID."}},
)
async def delete_subrace_image(
    subrace_id: int,
    image_service: SubraceImageDep,
    _: GmUserDep,
):
    """Remove the subrace's image from storage and clear its ``image_url``. **GM only.**"""

    await image_service.delete_image(subrace_id)
    return None
