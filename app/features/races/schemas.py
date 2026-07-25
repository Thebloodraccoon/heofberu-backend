from pydantic import BaseModel, ConfigDict


class RaceBase(BaseModel):
    name: str
    size: str = "Средний"
    speed: int = 30
    ability_bonuses: dict = {}
    granted_skills: list = []
    traits: str = ""
    description: str = ""
    is_homebrew: bool = False


class RaceCreate(RaceBase):
    pass


class RaceUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    size: str | None = None
    speed: int | None = None
    ability_bonuses: dict | None = None
    granted_skills: list | None = None
    traits: str | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class RaceResponse(RaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
