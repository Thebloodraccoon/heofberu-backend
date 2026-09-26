"""Article image endpoints (mounted under ``/articles/{article_id}``)."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.features.articles.dependencies import ArticleImagesDep
from app.features.articles.images.schemas import ArticleImageResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/images",
    response_model=list[ArticleImageResponse],
    summary="List images uploaded for an article",
    responses={404: {"description": "No article exists with the given ID."}},
)
async def list_article_images(article_id: int, article_service: ArticleImagesDep, _: GmUserDep):
    """
    Return every image uploaded for the article, oldest first. **GM only.**

    Readers see images only where `body_markdown` embeds them — this list is for
    the editor (reuse/delete), and would otherwise expose images placed inside
    `:::gm` blocks or not used in the text at all.
    """

    return await article_service.list_images(article_id)


@router.post(
    "/images",
    response_model=ArticleImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image for an article",
    responses={
        400: {"description": "Invalid or oversized image, or the upload failed."},
        404: {"description": "No article exists with the given ID."},
    },
)
async def upload_article_image(
    article_id: int,
    article_service: ArticleImagesDep,
    _: GmUserDep,
    image: Annotated[UploadFile, File(description="Image file (JPEG, PNG, WebP or GIF, max 5 MB).")],
):
    """
    Upload a new image for the article and return it, with the public URL to embed
    in `body_markdown` as `![alt](image_url)`. **GM only.**
    """

    return await article_service.upload_image(article_id, image)


@router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an article image",
    responses={404: {"description": "No article or image exists with the given IDs."}},
)
async def delete_article_image(article_id: int, image_id: int, article_service: ArticleImagesDep, _: GmUserDep):
    """Remove a single image of the article, from storage and the DB. **GM only.**"""

    await article_service.delete_image(article_id, image_id)
    return None
