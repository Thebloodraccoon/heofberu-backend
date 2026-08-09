"""Schemas for recording features on a character."""

from pydantic import BaseModel, ConfigDict

from app.features.features.schemas import FeatureGetAllResponse


class CharacterFeatureAdd(BaseModel):
    """
    Record a reference feature on a character.

    ``notes`` is an optional per-character annotation (e.g. choices made
    within the feature, like a Fighting Style pick); defaults to an empty
    string.
    """

    feature_id: int
    notes: str = ""


class CharacterFeatureUpdate(BaseModel):
    """
    Replace the notes on an already-recorded feature.

    Send ``notes: ""`` to clear them. There's no way to change
    ``feature_id`` itself — remove the grant and add a new one instead.
    """

    notes: str | None = None


class CharacterFeatureResponse(BaseModel):
    """
    Aggregates a character's feature grant with its per-character notes
    and a *brief* summary of the referenced feature (id, name, source_type,
    level, is_homebrew).

    Deliberately does not embed the full feature body (description): a
    character can hold many features, and listing them should stay light.
    Full detail is fetched on demand through the open
    ``GET /features/{feature_id}`` endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feature_id: int
    notes: str = ""
    feature: FeatureGetAllResponse
