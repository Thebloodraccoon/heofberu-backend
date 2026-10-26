"""Schemas of a character's combat stats: the manual sheet values next to the computed ones."""

from pydantic import BaseModel

from app.constants import SpeedType


class CombatContribution(BaseModel):
    """
    One line of a computed value: ``source`` is its kind (``armor``/``shield``/``unarmored``/``ability``/
    ``formula``/``bonus`` for AC; ``base``/``set``/``equal_to_walk``/``bonus``/``penalty`` for speeds),
    ``label`` the feature/item/ability name, ``value`` its amount (for ``set``/``equal_to_walk``/``base``
    the speed it sets). An ``inactive`` line also carries ``reason`` — why it doesn't count right now
    (its source then may also be an effect mode: ``bonus``/``formula``/``set``/``equal_to_walk``/
    ``ignore_armor_penalty``) and ``reason_code``, its stable machine-readable form: ``base_lower``,
    ``condition_unmet``, ``level_too_low``, ``not_stacking``, ``speed_higher``, ``no_speed``.
    """

    source: str
    label: str
    value: int
    speed_type: SpeedType | None = None
    reason: str | None = None
    reason_code: str | None = None


class ArmorClassView(BaseModel):
    """``manual`` / ``shield_manual``: what the player wrote on the sheet; ``computed``: the engine's AC."""

    manual: int
    shield_manual: int
    computed: int
    breakdown: list[CombatContribution]
    # what reaches the character but doesn't count now (condition, level, a better base, a shield it excludes)
    inactive: list[CombatContribution] = []


class ComputedSpeeds(BaseModel):
    """Computed speeds in feet; ``None`` when the character doesn't have that kind of movement."""

    walk: int | None = None
    fly: int | None = None
    swim: int | None = None
    climb: int | None = None
    burrow: int | None = None


class SpeedView(BaseModel):
    """``manual``: the walking speed the player wrote on the sheet; ``computed``: every engine speed."""

    manual: int
    computed: ComputedSpeeds
    breakdown: list[CombatContribution]
    # what doesn't count now (condition, level, a bonus to a speed the character lacks, a lower set speed)
    inactive: list[CombatContribution] = []


class CharacterCombatStatsResponse(BaseModel):
    """``GET /characters/{id}/combat-stats``: AC and speeds, manual and computed."""

    armor_class: ArmorClassView
    speed: SpeedView
