"""Shared fixtures for game campaign and public campaign tests."""

import pytest_asyncio

from app.constants import UserRole


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def fighter(create_class):
    """One class for every character of a test (class names are unique)."""

    return await create_class(name="Fighter")


@pytest_asyncio.fixture
async def free_character(create_character, fighter, player):
    """The default player's character, in no campaign."""

    return await create_character(owner_id=player.id, class_id=fighter.id, name="Gurn", in_gm_campaign=False)


@pytest_asyncio.fixture
async def other_gm_token(create_user, login_as):
    """A second GM who runs nothing the tests set up."""

    return await login_as(await create_user(role=UserRole.GM))


@pytest_asyncio.fixture
async def make_campaign(client, gm_token):
    """Create a campaign through the API (as the default GM unless ``token`` is given)."""

    async def _make_campaign(token=None, **payload):
        body = {"title": "Nova, Vinnytsia branch", **payload}
        response = await client.post("/campaigns", json=body, headers=auth(token or gm_token))
        assert response.status_code == 201, response.text
        return response.json()

    return _make_campaign


@pytest_asyncio.fixture
async def add_character(client, gm_token):
    """Add a character to a campaign through the API (as the default GM unless ``token`` is given)."""

    async def _add_character(campaign_id, character_id, token=None):
        response = await client.post(
            f"/campaigns/{campaign_id}/characters", json={"character_id": character_id}, headers=auth(token or gm_token)
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _add_character


@pytest_asyncio.fixture
async def make_public_campaign(client, gm_token):
    """Create (and by default publish) a public campaign as the default GM."""

    async def _make_public_campaign(publish=True, **payload):
        body = {"title": "Curse of the Lighthouse", "pitch": "A one-shot by the sea", **payload}
        response = await client.post("/public-campaigns", json=body, headers=auth(gm_token))
        assert response.status_code == 201, response.text
        preset = response.json()
        if publish:
            published = await client.post(f"/public-campaigns/{preset['id']}/publish", headers=auth(gm_token))
            assert published.status_code == 200, published.text
            preset = published.json()
        return preset

    return _make_public_campaign
