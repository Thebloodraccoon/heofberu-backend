"""Unit tests for the attacks / conditions / backstory request schemas (bounds and PATCH nulls)."""

from pydantic import ValidationError
import pytest

from app.constants import BACKSTORY_MAX_LENGTH, ConditionType
from app.features.characters.attacks.schemas import AttackCreate, AttackUpdate
from app.features.characters.backstory.schemas import CharacterBackstoryUpdate
from app.features.characters.conditions.schemas import CharacterConditionAdd, CharacterConditionUpdate

ATTACK = {"name": "Longsword", "attack_type": "MELEE_ATTACK", "ability": "STR"}


@pytest.mark.unit
class TestAttackSchemas:
    def test_valid_attack_defaults(self):
        attack = AttackCreate(**ATTACK)

        assert attack.is_proficient is True
        assert attack.range == ""

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": ""},
            {"name": "x" * 201},
            {"range": "x" * 51},
            {"notes": "x" * 5_001},
            {"bonus_attack": 101},
            {"bonus_damage": -101},
            {"damage_dice_count": 0},
            {"damage_dice_count": -2},
            {"damage_dice_count": 101},
        ],
    )
    def test_out_of_bounds_values_are_rejected(self, overrides):
        with pytest.raises(ValidationError):
            AttackCreate(**{**ATTACK, **overrides})

    def test_dice_count_may_be_omitted(self):
        assert AttackCreate(**ATTACK).damage_dice_count is None

    @pytest.mark.parametrize(
        "field", ["name", "attack_type", "ability", "is_proficient", "bonus_attack", "bonus_damage", "range", "notes"]
    )
    def test_patch_rejects_null_for_non_nullable_fields(self, field):
        with pytest.raises(ValidationError) as exc_info:
            AttackUpdate(**{field: None})

        assert field in str(exc_info.value)

    @pytest.mark.parametrize("field", ["damage_dice_count", "damage_dice_type", "damage_type"])
    def test_patch_allows_clearing_the_nullable_damage_fields(self, field):
        update = AttackUpdate(**{field: None})

        assert update.model_dump(exclude_unset=True) == {field: None}

    def test_patch_without_fields_is_empty(self):
        assert AttackUpdate().model_dump(exclude_unset=True) == {}


@pytest.mark.unit
class TestConditionSchemas:
    def test_source_is_length_limited(self):
        with pytest.raises(ValidationError):
            CharacterConditionAdd(condition=ConditionType.POISONED, source="x" * 1_001)

    def test_patch_rejects_null_source(self):
        with pytest.raises(ValidationError) as exc_info:
            CharacterConditionUpdate(source=None)

        assert "source" in str(exc_info.value)

    def test_patch_allows_null_exhaustion_level(self):
        assert CharacterConditionUpdate(exhaustion_level=None).model_dump(exclude_unset=True) == {
            "exhaustion_level": None
        }

    def test_patch_source_only(self):
        assert CharacterConditionUpdate(source="cursed").model_dump(exclude_unset=True) == {"source": "cursed"}


@pytest.mark.unit
class TestBackstorySchema:
    def test_content_is_required(self):
        with pytest.raises(ValidationError):
            CharacterBackstoryUpdate()

    def test_empty_string_clears_the_backstory(self):
        assert CharacterBackstoryUpdate(content="").content == ""

    def test_content_is_capped(self):
        CharacterBackstoryUpdate(content="x" * BACKSTORY_MAX_LENGTH)
        with pytest.raises(ValidationError):
            CharacterBackstoryUpdate(content="x" * (BACKSTORY_MAX_LENGTH + 1))
