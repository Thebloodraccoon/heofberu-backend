"""Validation bounds of the race / subrace request schemas (malformed input fails with 422, not in the database)."""

from pydantic import ValidationError
import pytest

from app.constants import AbilityScore, RaceSize
from app.core.types import INT32_MAX
from app.features.races.crud.schemas import RaceCreate, RaceUpdate
from app.features.races.skills.schemas import SkillsUpdate
from app.features.shared.catalog.schemas import AbilityBonusesUpdate, AbilityBonusItem
from app.features.shared.tags.schemas import TagsUpdate
from app.features.subraces.crud.schemas import SubraceCreate, SubraceGetAllResponse, SubraceUpdate


@pytest.mark.unit
class TestRaceCreate:
    def test_defaults(self):
        race = RaceCreate(name="Elf")

        assert (race.size, race.speed, race.description) == (RaceSize.MEDIUM, 30, "")

    def test_name_is_trimmed(self):
        assert RaceCreate(name="  Elf  ").name == "Elf"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 101])
    def test_rejects_empty_or_overlong_name(self, name):
        with pytest.raises(ValidationError):
            RaceCreate(name=name)

    def test_accepts_name_of_exactly_100(self):
        assert len(RaceCreate(name="x" * 100).name) == 100

    @pytest.mark.parametrize("speed", [-1, 201, 10**9])
    def test_rejects_speed_out_of_range(self, speed):
        with pytest.raises(ValidationError):
            RaceCreate(name="Elf", speed=speed)

    @pytest.mark.parametrize("speed", [0, 30, 200])
    def test_accepts_speed_in_range(self, speed):
        assert RaceCreate(name="Elf", speed=speed).speed == speed

    def test_rejects_overlong_description(self):
        with pytest.raises(ValidationError):
            RaceCreate(name="Elf", description="x" * 10_001)

    def test_image_url_is_not_a_writable_field(self):
        assert "image_url" not in RaceCreate.model_fields
        assert "image_url" not in RaceCreate(name="Elf", image_url="https://evil.example/x.png").model_dump()
        assert "image_url" not in RaceUpdate.model_fields


@pytest.mark.unit
class TestPartialUpdates:
    @pytest.mark.parametrize("field", ["name", "size", "speed", "description"])
    def test_race_update_rejects_explicit_null(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            RaceUpdate(**{field: None})

    @pytest.mark.parametrize("field", ["name", "description"])
    def test_subrace_update_rejects_explicit_null(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            SubraceUpdate(**{field: None})

    def test_omitted_fields_stay_unset(self):
        assert RaceUpdate(speed=35).model_dump(exclude_unset=True) == {"speed": 35}
        assert SubraceUpdate().model_dump(exclude_unset=True) == {}

    def test_update_applies_the_same_bounds(self):
        with pytest.raises(ValidationError):
            RaceUpdate(speed=-5)
        with pytest.raises(ValidationError):
            RaceUpdate(name="x" * 101)
        with pytest.raises(ValidationError):
            SubraceUpdate(name="")
        with pytest.raises(ValidationError):
            SubraceUpdate(name="x" * 101)


@pytest.mark.unit
class TestSubraceCreate:
    def test_valid(self):
        subrace = SubraceCreate(name="High Elf", race_id=1)

        assert (subrace.race_id, subrace.description) == (1, "")

    @pytest.mark.parametrize("name", ["", " ", "x" * 101])
    def test_rejects_bad_name(self, name):
        with pytest.raises(ValidationError):
            SubraceCreate(name=name, race_id=1)

    @pytest.mark.parametrize("race_id", [0, -1, INT32_MAX + 1])
    def test_rejects_race_id_outside_int32_positive_range(self, race_id):
        with pytest.raises(ValidationError):
            SubraceCreate(name="High Elf", race_id=race_id)

    def test_brief_is_the_listing_shape(self):
        brief = SubraceGetAllResponse.model_validate({"id": 1, "race_id": 2, "name": "x", "image_url": None})

        assert brief.race_id == 2


@pytest.mark.unit
class TestAbilityBonuses:
    def test_accepts_one_bonus_per_ability(self):
        data = AbilityBonusesUpdate(ability_bonuses=[{"ability": a, "bonus": 1} for a in AbilityScore])

        assert len(data.ability_bonuses) == len(AbilityScore)

    @pytest.mark.parametrize("bonus", [-10, 0, 10])
    def test_accepts_bonus_in_range(self, bonus):
        assert AbilityBonusItem(ability=AbilityScore.DEX, bonus=bonus).bonus == bonus

    @pytest.mark.parametrize("bonus", [-11, 11, 10**9])
    def test_rejects_bonus_out_of_range(self, bonus):
        with pytest.raises(ValidationError):
            AbilityBonusItem(ability=AbilityScore.DEX, bonus=bonus)

    def test_rejects_duplicate_abilities(self):
        with pytest.raises(ValidationError, match="Duplicate ability"):
            AbilityBonusesUpdate(
                ability_bonuses=[{"ability": "DEX", "bonus": 1}, {"ability": "DEX", "bonus": 2}],
            )

    def test_rejects_more_bonuses_than_abilities(self):
        items = [{"ability": a, "bonus": 1} for a in AbilityScore] * 2

        with pytest.raises(ValidationError):
            AbilityBonusesUpdate(ability_bonuses=items)


@pytest.mark.unit
class TestIdLists:
    @pytest.mark.parametrize("schema,field", [(SkillsUpdate, "skill_ids"), (TagsUpdate, "tag_ids")])
    def test_valid_lists(self, schema, field):
        assert getattr(schema(**{field: []}), field) == []
        assert getattr(schema(**{field: [1, INT32_MAX]}), field) == [1, INT32_MAX]

    @pytest.mark.parametrize("schema,field", [(SkillsUpdate, "skill_ids"), (TagsUpdate, "tag_ids")])
    @pytest.mark.parametrize("ids", [[0], [-3], [INT32_MAX + 1], [1, 1], list(range(1, 102))])
    def test_rejects_invalid_lists(self, schema, field, ids):
        with pytest.raises(ValidationError):
            schema(**{field: ids})
