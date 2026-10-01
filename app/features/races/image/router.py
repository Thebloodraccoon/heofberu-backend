"""Race image endpoints: upload and delete a race's catalog image."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.core.types import EntityIdPath
from app.features.auth.dependencies import GmUserDep
from app.features.races.dependencies import RaceImageDep

router = APIRouter()


@router.put(
    "/{race_id:int}/image",
    response_model=dict[str, str],
    summary="Upload a race's image",
    responses={
        400: {"description": "Invalid or oversized image, or the upload failed."},
        404: {"description": "No race exists with the given ID."},
    },
)
async def upload_race_image(
    race_id: EntityIdPath,
    image_service: RaceImageDep,
    _: GmUserDep,
    image: Annotated[UploadFile, File(description="Image file (JPEG, PNG, WebP or GIF, max 5 MB).")],
):
    """
    Upload (or replace) the race's catalog image and return its public URL.
    **GM only.**
    """

    return {"image_url": await image_service.upload(race_id, image)}


@router.delete(
    "/{race_id:int}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a race's image",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def delete_race_image(
    race_id: EntityIdPath,
    image_service: RaceImageDep,
    _: GmUserDep,
):
    """Remove the race's image from storage and clear its ``image_url``. **GM only.**"""

    await image_service.delete_image(race_id)
    return None
