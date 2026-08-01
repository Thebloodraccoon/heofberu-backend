from pydantic import BaseModel, ConfigDict, model_validator

from app.constants import FeatureSourceType

# Which FK field must be set (and which two must be empty) for each source_type.
# CLASS and SUBCLASS both key off class_id; FEAT and OTHER require none of the three.
_REQUIRED_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "class_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.BACKGROUND: "background_id",
    FeatureSourceType.FEAT: None,
    FeatureSourceType.OTHER: None,
}
_ALL_SOURCE_FKS = ("class_id", "race_id", "background_id")


def _validate_source_fk_consistency(source_type: FeatureSourceType, values: dict) -> None:
    """
    Enforce that exactly the FK matching ``source_type`` is set, and the
    other two are left empty:
      - CLASS / SUBCLASS -> class_id required, race_id/background_id must be None
      - RACE             -> race_id required, class_id/background_id must be None
      - BACKGROUND       -> background_id required, class_id/race_id must be None
      - FEAT / OTHER     -> none of the three may be set
    """

    required_fk = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]

    for fk_name in _ALL_SOURCE_FKS:
        fk_value = values.get(fk_name)

        if fk_name == required_fk:
            if fk_value is None:
                raise ValueError(f"source_type='{source_type.value}' requires '{fk_name}' to be set.")
        else:
            if fk_value is not None:
                raise ValueError(
                    f"source_type='{source_type.value}' must not set '{fk_name}' (only '{required_fk}' applies)."
                    if required_fk
                    else f"source_type='{source_type.value}' must not set '{fk_name}'."
                )

    if source_type not in (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS) and values.get("level") is not None:
        raise ValueError("'level' is only meaningful when source_type is CLASS or SUBCLASS.")

    if source_type != FeatureSourceType.SUBCLASS and values.get("subclass_name"):
        raise ValueError("'subclass_name' is only meaningful when source_type is SUBCLASS.")


class FeatureBase(BaseModel):
    name: str
    source_type: FeatureSourceType

    class_id: int | None = None
    race_id: int | None = None
    background_id: int | None = None

    level: int | None = None
    subclass_name: str | None = None

    description: str = ""
    is_homebrew: bool = False

    @model_validator(mode="after")
    def validate_source_fk_consistency(self):
        _validate_source_fk_consistency(self.source_type, self.__dict__)
        return self


class FeatureCreate(FeatureBase):
    pass


class FeatureUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Because source_type/FK consistency depends on the *combination* of
    fields, and PATCH may only touch one of them, this validation can't be
    fully enforced from the partial payload alone — the service re-checks
    consistency against the merged (existing + incoming) state before
    persisting. See ``FeatureService.update_feature``.
    """

    name: str | None = None
    source_type: FeatureSourceType | None = None
    class_id: int | None = None
    race_id: int | None = None
    background_id: int | None = None
    level: int | None = None
    subclass_name: str | None = None
    description: str | None = None
    is_homebrew: bool | None = None


class FeatureResponse(FeatureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None


class FeatureBriefResponse(BaseModel):
    """Lightweight listing row: no description."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: FeatureSourceType
    class_id: int | None = None
    race_id: int | None = None
    background_id: int | None = None
    level: int | None = None
    is_homebrew: bool
