"""Article test fixtures shared across the article test modules."""

import pytest_asyncio

from app.constants import UserRole


@pytest_asyncio.fixture
async def other_gm(create_user):
    """A second GM, who did not write the articles the tests create."""

    return await create_user(role=UserRole.GM)


@pytest_asyncio.fixture
async def other_gm_token(other_gm, login_as):
    return await login_as(other_gm)
