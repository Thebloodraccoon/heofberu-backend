"""
Races on the character write paths, driven through the service layer with one session per task
(the HTTP client shares a single session, so it can't interleave real transactions).
"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.constants import UserRole
from app.features.characters.attacks.exceptions import AttackLimitReachedException
from app.features.characters.attacks.schemas import AttackCreate
from app.features.characters.attacks.service import CharacterAttackService
from app.features.characters.gm_panel.items.schemas import CharacterItemAdd
from app.features.characters.gm_panel.items.service import GmPanelItemService
from app.features.users.schemas import UserResponse
from app.models import Attack, CharacterItem
from app.settings import settings

ATTACK = AttackCreate(
    name="Longsword",
    attack_type="MELEE_ATTACK",
    ability="STR",
    damage_dice_count=1,
    damage_dice_type="D8",
    damage_type="SLASHING",
)


def _user(user, role):
    return UserResponse(
        id=user.id, username=user.username, email=user.email, role=role, created_at=datetime(2026, 1, 1)
    )


async def _in_own_session(operation):
    """Run ``operation(session)`` on its own session/connection."""

    session = settings.SessionLocal()
    try:
        return await operation(session)
    finally:
        await session.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestConcurrentCharacterWrites:
    async def test_parallel_attack_creates_never_exceed_the_limit(
        self, db_session, player, create_class, create_character, monkeypatch
    ):
        monkeypatch.setattr("app.features.characters.attacks.service.MAX_ATTACKS_PER_CHARACTER", 3)
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        user = _user(player, UserRole.PLAYER)

        async def create(session):
            return await CharacterAttackService(session).create_attack(character.id, ATTACK, user)

        results = await asyncio.gather(*(_in_own_session(create) for _ in range(8)), return_exceptions=True)

        assert sum(not isinstance(r, Exception) for r in results) == 3
        assert all(isinstance(r, AttackLimitReachedException) for r in results if isinstance(r, Exception))
        stored = await db_session.scalar(
            select(func.count()).select_from(Attack).where(Attack.character_id == character.id)
        )
        assert stored == 3

    async def test_parallel_item_adds_never_lose_quantity(
        self, db_session, player, gm, create_class, create_character, create_item
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        item = await create_item(name="Arrow")
        character_id, item_id = character.id, item.id
        gm_user = _user(gm, UserRole.GM)

        async def add(session):
            payload = CharacterItemAdd(item_id=item_id, quantity=2)
            return await GmPanelItemService(session).add_item(character_id, payload, gm_user)

        await asyncio.gather(*(_in_own_session(add) for _ in range(6)))

        stacks = (
            (await db_session.execute(select(CharacterItem).where(CharacterItem.character_id == character_id)))
            .scalars()
            .all()
        )
        assert [stack.quantity for stack in stacks] == [12]
