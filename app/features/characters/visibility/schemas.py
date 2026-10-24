"""Schemas of the public character card and the owner's visibility switch."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, CharacterPublicVisibility


class CharacterVisibilityUpdate(BaseModel):
    """``PATCH /characters/{id}/public-visibility`` body."""

    public_visibility: CharacterPublicVisibility


class CharacterVisibilityResponse(BaseModel):
    """The character's current public visibility."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    public_visibility: CharacterPublicVisibility


class PublicAbilityScores(BaseModel):
    """Six ability values on a ``FULL`` card: the base scores, or the totals with every bonus included."""

    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


class PublicSkillProficiency(BaseModel):
    """One skill the character is proficient in, on a ``FULL`` card."""

    skill_id: int
    is_expertise: bool


class PublicCharacterSummary(BaseModel):
    """
    Who a public character is: the row of the public campaign showcase (``GET /public-campaigns/{id}/characters``)
    and the head of the public card.
    """

    id: int
    name: str
    level: int
    class_id: int
    subclass_id: int | None = None
    race_id: int | None = None
    subrace_id: int | None = None
    background_id: int | None = None
    owner_username: str
    public_visibility: CharacterPublicVisibility


class PublicCharacterCard(PublicCharacterSummary):
    """
    ``GET /characters/{id}/public`` of a ``FULL`` character: the summary, plus the personality, backstory (``:::gm``
    blocks stripped), base and total ability scores, skill and saving-throw proficiencies (never armor/weapon ones).
    Inventory, spells and campaign data (chronicle, notes, reviews) are never here.
    """

    personality_traits: str | None = None
    ideals: str | None = None
    bonds: str | None = None
    flaws: str | None = None
    backstory: str | None = None
    base_ability_scores: PublicAbilityScores | None = None
    ability_scores: PublicAbilityScores | None = None
    skill_proficiencies: list[PublicSkillProficiency] | None = None
    saving_throw_proficiencies: list[AbilityScore] | None = None
