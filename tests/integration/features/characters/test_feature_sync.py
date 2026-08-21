"""Tests for automatic class/subclass feature grants (feature_sync)."""

import pytest


async def get_feature_ids(client, character_id, token):
    response = await client.get(
        f"/characters/{character_id}/features",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return {item["feature_id"] for item in response.json()}


@pytest.mark.integration
@pytest.mark.asyncio
class TestAutoGrantOnCreate:
    async def test_create_grants_class_features_at_or_below_level(
        self, client, player, gm_token, create_class, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        second_wind = await create_feature(
            name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1
        )
        uncanny_dodge = await create_feature(
            name="Uncanny Dodge", source_type="CLASS", class_id=character_class.id, level=None
        )
        await create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)

        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        assert await get_feature_ids(client, character["id"], gm_token) == {second_wind.id, uncanny_dodge.id}

    async def test_create_with_subclass_grants_subclass_features(
        self, client, player, gm_token, create_class, create_subclass, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        improved_critical = await create_feature(
            name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=1
        )

        character, _ = await create_api_character(class_id=character_class.id, owner=player, subclass_id=subclass.id)

        assert await get_feature_ids(client, character["id"], gm_token) == {improved_critical.id}

    async def test_create_without_subclass_grants_no_subclass_features(
        self, client, player, gm_token, create_class, create_subclass, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        await create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=3)

        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        assert await get_feature_ids(client, character["id"], gm_token) == set()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAutoGrantOnLevelUp:
    async def test_level_up_grants_newly_unlocked_class_feature(
        self, client, player, player_token, create_class, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        action_surge = await create_feature(
            name="Action Surge", source_type="CLASS", class_id=character_class.id, level=2
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        assert await get_feature_ids(client, character["id"], player_token) == set()

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["level"] == 2
        assert await get_feature_ids(client, character["id"], player_token) == {action_surge.id}

    async def test_level_up_grants_newly_unlocked_subclass_feature(
        self,
        client,
        player,
        player_token,
        create_class,
        create_subclass,
        create_feature,
        create_api_character,
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        remarkable_athlete = await create_feature(
            name="Remarkable Athlete", source_type="SUBCLASS", subclass_id=subclass.id, level=2
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player, subclass_id=subclass.id)
        assert await get_feature_ids(client, character["id"], player_token) == set()

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert await get_feature_ids(client, character["id"], player_token) == {remarkable_athlete.id}

    async def test_manual_other_source_feature_survives_level_up(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        action_surge = await create_feature(
            name="Action Surge", source_type="CLASS", class_id=character_class.id, level=2
        )
        manual = await create_feature(name="Custom Gift", source_type="OTHER")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        # Manual (OTHER-source) grants are a GM-panel write.
        add_response = await client.post(
            f"/characters/{character['id']}/gm-panel/features",
            json={"feature_id": manual.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        assert await get_feature_ids(client, character["id"], player_token) == {action_surge.id, manual.id}


@pytest.mark.integration
@pytest.mark.asyncio
class TestAutoRevokeOnChange:
    async def test_class_change_revokes_old_grants_and_grants_new(
        self, client, player, player_token, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        fighting_style = await create_feature(name="Fighting Style", source_type="CLASS", class_id=fighter.id, level=1)
        arcane_recovery = await create_feature(name="Arcane Recovery", source_type="CLASS", class_id=wizard.id, level=1)
        character, _ = await create_api_character(class_id=fighter.id, owner=player)
        assert await get_feature_ids(client, character["id"], player_token) == {fighting_style.id}

        response = await client.patch(
            f"/characters/{character['id']}/progression/class",
            json={"class_id": wizard.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["class_id"] == wizard.id
        assert await get_feature_ids(client, character["id"], player_token) == {arcane_recovery.id}

    async def test_class_change_keeps_manual_other_source_feature(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        await create_feature(name="Fighting Style", source_type="CLASS", class_id=fighter.id, level=1)
        arcane_recovery = await create_feature(name="Arcane Recovery", source_type="CLASS", class_id=wizard.id, level=1)
        manual = await create_feature(name="Custom Gift", source_type="OTHER")
        character, _ = await create_api_character(class_id=fighter.id, owner=player)

        add_response = await client.post(
            f"/characters/{character['id']}/gm-panel/features",
            json={"feature_id": manual.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201

        response = await client.patch(
            f"/characters/{character['id']}/progression/class",
            json={"class_id": wizard.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        assert await get_feature_ids(client, character["id"], player_token) == {arcane_recovery.id, manual.id}

    async def test_set_subclass_grants_and_clear_revokes_features(
        self, client, player, player_token, create_class, create_subclass, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        improved_critical = await create_feature(
            name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=1
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        assert await get_feature_ids(client, character["id"], player_token) == set()

        set_response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": subclass.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert set_response.status_code == 200
        assert set_response.json()["subclass_id"] == subclass.id
        assert await get_feature_ids(client, character["id"], player_token) == {improved_critical.id}

        clear_response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["subclass_id"] is None
        assert await get_feature_ids(client, character["id"], player_token) == set()


@pytest.mark.integration
@pytest.mark.asyncio
class TestManualGrantInteractions:
    async def test_adding_already_auto_granted_feature_returns_409(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        second_wind = await create_feature(
            name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        assert await get_feature_ids(client, character["id"], player_token) == {second_wind.id}

        response = await client.post(
            f"/characters/{character['id']}/gm-panel/features",
            json={"feature_id": second_wind.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceBackgroundFeatAutoGrant:
    async def test_create_grants_race_features(
        self, client, player, player_token, create_race, create_class, create_feature, create_api_character
    ):
        race = await create_race(name="Elf")
        darkvision = await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, race_id=race.id)

        assert await get_feature_ids(client, character["id"], player_token) == {darkvision.id}

    async def test_create_without_race_grants_no_race_features(
        self, client, player, player_token, create_race, create_class, create_feature, create_api_character
    ):
        race = await create_race(name="Elf")
        await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        assert await get_feature_ids(client, character["id"], player_token) == set()

    async def test_change_race_revokes_old_grants_and_grants_new(
        self, client, player, player_token, create_race, create_class, create_feature, create_api_character
    ):
        elf = await create_race(name="Elf")
        darkvision = await create_feature(name="Darkvision", source_type="RACE", race_id=elf.id)
        dwarf = await create_race(name="Dwarf")
        dwarven_toughness = await create_feature(name="Dwarven Toughness", source_type="RACE", race_id=dwarf.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, race_id=elf.id)
        assert await get_feature_ids(client, character["id"], player_token) == {darkvision.id}

        response = await client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": dwarf.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["race_id"] == dwarf.id
        assert await get_feature_ids(client, character["id"], player_token) == {dwarven_toughness.id}

    async def test_clearing_race_revokes_race_features(
        self, client, player, player_token, create_race, create_class, create_feature, create_api_character
    ):
        elf = await create_race(name="Elf")
        darkvision = await create_feature(name="Darkvision", source_type="RACE", race_id=elf.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, race_id=elf.id)
        assert await get_feature_ids(client, character["id"], player_token) == {darkvision.id}

        response = await client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["race_id"] is None
        assert await get_feature_ids(client, character["id"], player_token) == set()

    async def test_create_grants_background_features(
        self, client, player, player_token, create_background, create_class, create_feature, create_api_character
    ):
        background = await create_background(name="Acolyte")
        shelter = await create_feature(
            name="Shelter of the Faithful", source_type="BACKGROUND", background_id=background.id
        )
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, background_id=background.id
        )

        assert await get_feature_ids(client, character["id"], player_token) == {shelter.id}

    async def test_feat_grant_grants_features_and_revoke_revokes_them(
        self,
        client,
        gm,
        gm_token,
        create_class,
        create_feat,
        create_feature,
        create_api_character,
    ):
        character_class = await create_class(name="Fighter")
        feat = await create_feat(name="Alert")
        alert_benefit = await create_feature(name="Alert Initiative", source_type="FEAT", feat_id=feat.id)
        character, _ = await create_api_character(class_id=character_class.id, owner=gm)
        assert await get_feature_ids(client, character["id"], gm_token) == set()

        add_response = await client.post(
            f"/characters/{character['id']}/gm-panel/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert add_response.status_code == 201
        assert await get_feature_ids(client, character["id"], gm_token) == {alert_benefit.id}

        character_feat_id = add_response.json()["id"]
        remove_response = await client.delete(
            f"/characters/{character['id']}/gm-panel/feats/{character_feat_id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove_response.status_code == 204
        assert await get_feature_ids(client, character["id"], gm_token) == set()

    async def test_race_and_background_features_survive_level_up(
        self,
        client,
        player,
        player_token,
        create_race,
        create_background,
        create_class,
        create_feature,
        create_api_character,
    ):
        race = await create_race(name="Elf")
        darkvision = await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)
        background = await create_background(name="Acolyte")
        shelter = await create_feature(
            name="Shelter of the Faithful", source_type="BACKGROUND", background_id=background.id
        )
        character_class = await create_class(name="Fighter", hit_dice="D10")
        action_surge = await create_feature(
            name="Action Surge", source_type="CLASS", class_id=character_class.id, level=2
        )
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, background_id=background.id
        )
        assert await get_feature_ids(client, character["id"], player_token) == {darkvision.id, shelter.id}

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        assert await get_feature_ids(client, character["id"], player_token) == {
            darkvision.id,
            shelter.id,
            action_surge.id,
        }

    async def test_create_grants_subrace_features(
        self,
        client,
        player,
        player_token,
        create_race,
        create_subrace,
        create_class,
        create_feature,
        create_api_character,
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        weapon_training = await create_feature(name="Elf Weapon Training", source_type="SUBRACE", subrace_id=subrace.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id
        )

        assert await get_feature_ids(client, character["id"], player_token) == {weapon_training.id}

    async def test_create_without_subrace_grants_no_subrace_features(
        self,
        client,
        player,
        player_token,
        create_race,
        create_subrace,
        create_class,
        create_feature,
        create_api_character,
    ):
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        await create_feature(name="Elf Weapon Training", source_type="SUBRACE", subrace_id=subrace.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, race_id=race.id)

        assert await get_feature_ids(client, character["id"], player_token) == set()

    async def test_race_and_subrace_features_both_present(
        self,
        client,
        player,
        player_token,
        create_race,
        create_subrace,
        create_class,
        create_feature,
        create_api_character,
    ):
        """Race features and subrace features must coexist — subrace does NOT replace race features."""
        race = await create_race(name="Elf")
        darkvision = await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        weapon_training = await create_feature(name="Elf Weapon Training", source_type="SUBRACE", subrace_id=subrace.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id
        )

        feature_ids = await get_feature_ids(client, character["id"], player_token)
        assert feature_ids == {darkvision.id, weapon_training.id}

    async def test_change_subrace_grants_new_and_revokes_old(
        self,
        client,
        player,
        player_token,
        create_race,
        create_subrace,
        create_class,
        create_feature,
        create_api_character,
    ):
        elf = await create_race(name="Elf")
        high_elf = await create_subrace(race_id=elf.id, name="High Elf")
        weapon_training = await create_feature(
            name="Elf Weapon Training", source_type="SUBRACE", subrace_id=high_elf.id
        )
        drow = await create_subrace(race_id=elf.id, name="Drow")
        drow_magic = await create_feature(name="Drow Magic", source_type="SUBRACE", subrace_id=drow.id)
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=elf.id, subrace_id=high_elf.id
        )
        assert await get_feature_ids(client, character["id"], player_token) == {weapon_training.id}

        response = await client.patch(
            f"/characters/{character['id']}/progression/subrace",
            json={"subrace_id": drow.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["subrace_id"] == drow.id
        assert await get_feature_ids(client, character["id"], player_token) == {drow_magic.id}
