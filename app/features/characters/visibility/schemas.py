"""Schemas of the public character card and the owner's visibility switch."""

from pydantic import BaseModel, ConfigDict

from app.constants import CharacterPublicVisibility


class CharacterVisibilityUpdate(BaseModel):
    """``PATCH /characters/{id}/public-visibility`` body."""

    public_visibility: CharacterPublicVisibility


class CharacterVisibilityResponse(BaseModel):
    """The character's current public visibility."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    public_visibility: CharacterPublicVisibility


class PublicAbilityScores(BaseModel):
    """Ability totals (bonuses included) as shown on a ``FULL`` card."""

    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


class PublicItem(BaseModel):
    """One inventory stack on a ``FULL`` card."""

    name: str
    quantity: int


class PublicCharacterConcept(BaseModel):
    """
    What ``CONCEPT`` shows: who the character is, never how it plays.

    Also the row of the public campaign showcase (``GET /public-campaigns/{id}/characters``), whatever the level.
    """

    id: int
    name: str
    level: int
    class_name: str
    subclass_name: str | None = None
    race_name: str | None = None
    subrace_name: str | None = None
    owner_username: str
    public_visibility: CharacterPublicVisibility


class PublicCharacterCard(PublicCharacterConcept):
    """
    ``GET /characters/{id}/public``: the concept, plus for ``FULL`` the personality, backstory (``:::gm`` blocks
    stripped), ability totals, inventory and spells. Campaign data (chronicle, notes, reviews) is never here.
    """

    personality_traits: str | None = None
    ideals: str | None = None
    bonds: str | None = None
    flaws: str | None = None
    backstory: str | None = None
    ability_scores: PublicAbilityScores | None = None
    items: list[PublicItem] | None = None
    spells: list[str] | None = None
