"""
Integration tests for the hardened character crud endpoints: listing roles and
ordering, PATCH bounds/nulls/permissions, response-cache invalidation, atomic
rest and concurrent HP changes.
"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select

from app.constants import AbilityScore, SpellLevel, UserRole
from app.features.characters.cache import character_cache_key
from app.features.characters.crud.schemas import HpUpdate
from app.features.characters.crud.service import CharacterService
from app.features.users.schemas import UserResponse
from app.models import Character, CharacterSpellSlot, RaceAbilityBonus
from app.settings import settings


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def caching_on(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)


@pytest.mark.integration
@pytest.mark.asyncio
class TestListingRoles:
    async def test_mine_returns_only_own_characters_even_for_a_gm(
        self, client, gm, gm_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=gm.id, class_id=fighter.id, name="GM Hero")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Player Hero")

        response = await client.get("/characters", params={"scope": "mine"}, headers=auth(gm_token))

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["GM Hero"]

    async def test_all_is_gm_only(self, client, player_token):
        response = await client.get("/characters", params={"scope": "all"}, headers=auth(player_token))

        assert response.status_code == 403

    async def test_all_lists_every_users_characters_for_a_gm(
        self, client, gm_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Aragorn")

        response = await client.get("/characters", params={"scope": "all"}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_all_lists_every_users_characters_for_a_founder(
        self, client, founder_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Aragorn")

        response = await client.get("/characters", params={"scope": "all"}, headers=auth(founder_token))

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_default_scope_is_mine_even_for_a_gm(
        self, client, gm, gm_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=gm.id, class_id=fighter.id, name="GM Hero")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Player Hero")

        response = await client.get("/characters", headers=auth(gm_token))

        assert [item["name"] for item in response.json()["items"]] == ["GM Hero"]

    async def test_unknown_scope_is_rejected(self, client, gm_token):
        response = await client.get("/characters", params={"scope": "everyone"}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_all_scope_combines_with_filters(self, client, gm_token, player, create_class, create_character):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Aragorn")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Legolas")

        response = await client.get("/characters", params={"scope": "all", "search": "ara"}, headers=auth(gm_token))

        assert [item["name"] for item in response.json()["items"]] == ["Aragorn"]

    async def test_founder_sees_every_character_with_scope_all(
        self, client, founder_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Aragorn")

        response = await client.get("/characters", params={"scope": "all"}, headers=auth(founder_token))

        assert [item["name"] for item in response.json()["items"]] == ["Aragorn"]

    async def test_founder_can_read_and_edit_another_users_character(
        self, client, founder_token, player, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        get_response = await client.get(f"/characters/{character.id}", headers=auth(founder_token))
        patch_response = await client.patch(
            f"/characters/{character.id}", json={"notes": "founder note"}, headers=auth(founder_token)
        )

        assert get_response.status_code == 200
        assert patch_response.status_code == 200
        assert patch_response.json()["notes"] == "founder note"

    async def test_same_named_characters_page_in_a_stable_order(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        created = [(await create_character(owner_id=player.id, class_id=fighter.id, name="Twin")).id for _ in range(3)]

        seen = []
        for page in (1, 2, 3):
            response = await client.get("/characters", params={"page": page, "size": 1}, headers=auth(player_token))
            seen.extend(item["id"] for item in response.json()["items"])

        assert seen == created

    async def test_cursor_pagination_walks_every_character_once_in_order(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        created = [(await create_character(owner_id=player.id, class_id=fighter.id, name="Twin")).id for _ in range(3)]
        await create_character(owner_id=player.id, class_id=fighter.id, name="Aaron")

        seen, cursor, pages = [], None, 0
        while True:
            params = {"pagination": "cursor", "size": 2}
            if cursor:
                params["cursor"] = cursor
            body = (await client.get("/characters", params=params, headers=auth(player_token))).json()
            assert set(body) == {"items", "next_cursor", "size"}
            seen.extend(item["id"] for item in body["items"])
            pages += 1
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert pages == 2
        assert seen[1:] == created and len(seen) == 4

    async def test_cursor_keeps_scope_authorization(self, client, player_token):
        response = await client.get(
            "/characters", params={"scope": "all", "pagination": "cursor"}, headers=auth(player_token)
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("cursor", ["not-a-cursor", "e30", "x" * 600])
    async def test_invalid_cursor_is_rejected(self, client, player_token, cursor):
        response = await client.get("/characters", params={"cursor": cursor}, headers=auth(player_token))

        assert response.status_code == 422

    async def test_oversized_search_is_rejected(self, client, player_token):
        response = await client.get("/characters", params={"search": "x" * 201}, headers=auth(player_token))

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterPatchValidation:
    @pytest.mark.parametrize(
        "field",
        ["name", "armor_class", "shield", "speed", "current_hp", "temp_hp", "inspiration", "notes", "money_gold"],
    )
    async def test_explicit_null_is_a_422_not_a_database_error(
        self, client, player, player_token, create_class, create_character, field
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.patch(f"/characters/{character.id}", json={field: None}, headers=auth(player_token))

        assert response.status_code == 422
        assert field in response.text

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": ""},
            {"name": "x" * 201},
            {"money_gold": 3_000_000_000},
            {"money_copper": -1},
            {"armor_class": 100_000},
            {"temp_hp": 10**9},
            {"notes": "x" * 20_001},
            {"ideals": "x" * 5_001},
        ],
    )
    async def test_out_of_bounds_values_are_a_422(
        self, client, player, player_token, create_class, create_character, payload
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.patch(f"/characters/{character.id}", json=payload, headers=auth(player_token))

        assert response.status_code == 422

    async def test_current_hp_patch_is_clamped_to_max_hp(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=20, current_hp=5)

        response = await client.patch(
            f"/characters/{character.id}", json={"current_hp": 999}, headers=auth(player_token)
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 20

    async def test_name_is_trimmed(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.patch(
            f"/characters/{character.id}", json={"name": "  Boromir  "}, headers=auth(player_token)
        )

        assert response.json()["name"] == "Boromir"

    async def test_hp_endpoint_rejects_absurd_values(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=10, current_hp=10)

        for body in ({"temp_hp": 10**9}, {"delta": -(10**9)}, {"current_hp": 10**9}):
            response = await client.patch(f"/characters/{character.id}/hp", json=body, headers=auth(player_token))
            assert response.status_code == 422

    async def test_create_rejects_blank_and_oversized_values(self, client, player_token, create_class):
        fighter = await create_class(name="Fighter")

        for overrides in ({"name": ""}, {"name": "x" * 201}, {"money_gold": 3_000_000_000}, {"notes": "x" * 20_001}):
            response = await client.post(
                "/characters",
                json={"name": "Valid", "class_id": fighter.id, **overrides},
                headers=auth(player_token),
            )
            assert response.status_code == 422, overrides


@pytest.mark.integration
@pytest.mark.asyncio
class TestInspirationPermissions:
    async def test_player_cannot_raise_own_inspiration(
        self, client, player, player_token, create_class, create_character, db_session
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, inspiration=1)

        response = await client.patch(
            f"/characters/{character.id}", json={"inspiration": 5}, headers=auth(player_token)
        )

        assert response.status_code == 403
        await db_session.refresh(character)
        assert character.inspiration == 1

    async def test_player_can_spend_inspiration(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, inspiration=3)

        response = await client.patch(
            f"/characters/{character.id}", json={"inspiration": 2}, headers=auth(player_token)
        )

        assert response.status_code == 200
        assert response.json()["inspiration"] == 2

    async def test_gm_can_grant_inspiration(self, client, gm_token, player, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        response = await client.patch(f"/characters/{character.id}", json={"inspiration": 4}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["inspiration"] == 4


@pytest.mark.integration
@pytest.mark.asyncio
class TestResponseCache:
    async def test_get_caches_the_response_with_a_short_ttl(
        self, client, redis_client, caching_on, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)

        await client.get(f"/characters/{character.id}", headers=auth(player_token))

        key = character_cache_key(character.id)
        assert await redis_client.exists(key) == 1
        assert 0 < await redis_client.ttl(key) <= 300

    async def test_patch_purges_the_exact_key_and_the_next_read_is_fresh(
        self, client, redis_client, caching_on, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, name="Old")
        await client.get(f"/characters/{character.id}", headers=auth(player_token))

        await client.patch(f"/characters/{character.id}", json={"name": "New"}, headers=auth(player_token))

        assert await redis_client.exists(character_cache_key(character.id)) == 0
        read = await client.get(f"/characters/{character.id}", headers=auth(player_token))
        assert read.json()["name"] == "New"

    async def test_hp_update_rest_and_delete_purge_the_key(
        self, client, redis_client, caching_on, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=20, current_hp=20)
        key = character_cache_key(character.id)

        for method, path, body in (
            ("patch", f"/characters/{character.id}/hp", {"delta": -3}),
            ("post", f"/characters/{character.id}/rest", {"type": "long"}),
            ("delete", f"/characters/{character.id}", None),
        ):
            await client.get(f"/characters/{character.id}", headers=auth(player_token))
            assert await redis_client.exists(key) == 1
            kwargs = {"json": body} if body is not None else {}
            response = await getattr(client, method)(path, headers=auth(player_token), **kwargs)
            assert response.status_code in (200, 204)
            assert await redis_client.exists(key) == 0, path

    async def test_access_control_is_not_served_from_the_cache(
        self,
        client,
        redis_client,
        caching_on,
        player,
        player_token,
        create_user,
        login_as,
        create_class,
        create_character,
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        await client.get(f"/characters/{character.id}", headers=auth(player_token))
        intruder = await create_user(username="intruder", email="intruder@example.com")

        response = await client.get(f"/characters/{character.id}", headers=auth(await login_as(intruder)))

        assert response.status_code == 403

    async def test_conditions_do_not_touch_the_character_cache(
        self, client, redis_client, caching_on, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id)
        await client.get(f"/characters/{character.id}", headers=auth(player_token))

        await client.post(
            f"/characters/{character.id}/conditions", json={"condition": "POISONED"}, headers=auth(player_token)
        )

        assert await redis_client.exists(character_cache_key(character.id)) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestRest:
    async def test_long_rest_resets_used_spell_slots(
        self, client, db_session, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=20, current_hp=3, temp_hp=2)
        db_session.add(CharacterSpellSlot(character_id=character.id, spell_level=SpellLevel.LEVEL_1, total=3, used=2))
        await db_session.commit()

        response = await client.post(
            f"/characters/{character.id}/rest", json={"type": "long"}, headers=auth(player_token)
        )

        assert response.status_code == 200
        assert (response.json()["current_hp"], response.json()["temp_hp"]) == (20, 0)
        used = await db_session.scalar(
            select(CharacterSpellSlot.used)
            .where(CharacterSpellSlot.character_id == character.id)
            .execution_options(populate_existing=True)
        )
        assert used == 0

    async def test_long_rest_is_atomic_when_the_slot_reset_fails(
        self, client, db_session, monkeypatch, player, player_token, create_class, create_character
    ):
        from app.features.characters.spells.repository import CharacterSpellSlotRepository

        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=20, current_hp=3)

        async def broken_reset(self, character_id, *, commit=True):
            raise RuntimeError("slot reset failed")

        monkeypatch.setattr(CharacterSpellSlotRepository, "reset_all_spell_slots", broken_reset)
        character_id = character.id

        with pytest.raises(RuntimeError):
            await client.post(f"/characters/{character_id}/rest", json={"type": "long"}, headers=auth(player_token))

        current_hp = await db_session.scalar(
            select(Character.current_hp).where(Character.id == character_id).execution_options(populate_existing=True)
        )
        assert current_hp == 3

    async def test_short_rest_changes_nothing(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=20, current_hp=3)

        response = await client.post(
            f"/characters/{character.id}/rest", json={"type": "short"}, headers=auth(player_token)
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestConcurrentHp:
    async def test_parallel_damage_is_never_lost(self, db_session, player, create_class, create_character):
        fighter = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=fighter.id, max_hp=100, current_hp=100)
        user = UserResponse(
            id=player.id,
            username=player.username,
            email=player.email,
            role=UserRole.PLAYER,
            created_at=datetime(2026, 1, 1),
        )

        async def hit():
            session = settings.SessionLocal()
            try:
                await CharacterService(session).update_hp(character.id, HpUpdate(delta=-5), user)
            finally:
                await session.close()

        await asyncio.gather(*(hit() for _ in range(8)))

        current_hp = await db_session.scalar(
            select(Character.current_hp).where(Character.id == character.id).execution_options(populate_existing=True)
        )
        assert current_hp == 60


@pytest.mark.integration
@pytest.mark.asyncio
class TestStatsBreakdown:
    async def test_stats_label_the_race_contribution_with_the_race_name(
        self, client, db_session, player, player_token, create_race, create_class, create_api_character
    ):
        elf = await create_race(name="Elf")
        db_session.add(RaceAbilityBonus(race_id=elf.id, ability=AbilityScore.DEX, bonus=2))
        await db_session.commit()
        fighter = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id, dexterity=12)

        response = await client.get(f"/characters/{character['id']}/stats", headers=auth(token))

        dexterity = response.json()["dexterity"]
        assert (dexterity["base"], dexterity["total"]) == (12, 14)
        assert dexterity["contributions"] == [{"source": "race", "label": "Elf", "amount": 2}]
        assert response.json()["strength"]["contributions"] == []
        assert character["ability_scores"]["dexterity_total"] == 14
