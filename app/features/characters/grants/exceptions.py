"""Character grant (effect-engine) exceptions."""

from fastapi import status

from app.core.exceptions import AppError


class GrantNotFoundError(AppError):
    """Raised (404) when a character_feature grant doesn't exist for the character."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, character_id: int, grant_id: int):
        """Initialize with both ids for a clear message."""
        super().__init__(f"Feature grant {grant_id} not found on character {character_id}.")


class ChoiceGroupNotFoundError(AppError):
    """Raised (404) when a grant has no such choice group (stale client)."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, grant_id: int, group_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Choice group {group_id} not found on feature grant {grant_id}.")


class ChoiceOptionNotFoundError(AppError):
    """Raised (404) when a chosen option doesn't belong to the group (stale client)."""

    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, group_id: int, option_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Choice option {option_id} not found in choice group {group_id}.")


class ChoiceOptionAlreadyPickedError(AppError):
    """Raised (409) when a request re-picks an option already selected for the group."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, group_id: int, option_id: int):
        """Initialize with the offending ids."""
        super().__init__(f"Option {option_id} is already picked for choice group {group_id}.")


class ChoiceCountMismatchError(AppError):
    """Raised (422) when a group is answered with the wrong number of options."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, group_id: int, pick_count: int, given: int):
        """Initialize with the expected vs actual count."""
        super().__init__(f"Choice group {group_id} requires exactly {pick_count} option(s); received {given}.")


class SkillPickRequiredError(AppError):
    """Raised (422) when an "any skill" (open) option is picked without naming the skill."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has an open ('any skill') skill effect — name the skill in 'skill_id'.")


class UnexpectedSkillPickError(AppError):
    """Raised (422) when an answer names a ``skill_id`` for an option that has no open skill effect."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has no open ('any skill') skill effect — 'skill_id' must not be set.")


class UnknownSkillPickError(AppError):
    """Raised (422) when an answer names skills that don't exist."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, skill_ids: list[int]):
        """Initialize with the unknown ids."""
        super().__init__(f"Unknown skill_id(s): {skill_ids}.")


class SkillPickNotAllowedError(AppError):
    """
    Raised (422) when a skill option's effect doesn't fit the character's
    other sources: proficiency it already has, expertise without the
    proficiency, or expertise it already has.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int, skill_id: int, reason: str):
        """Initialize with the offending option/skill and why the pick is refused."""
        super().__init__(f"Option {option_id} can't be taken for skill {skill_id}: {reason}.")


class AbilityPickCapExceededError(AppError):
    """
    Raised (400) when a picked ability-score option takes the score above the cap of 20 (or the option's own
    ``new_cap``): the player's structured choices are capped there — a feat's ASI pick included.
    """

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, ability: str, current_total: int, requested: int, cap: int = 20):
        """Initialize with the ability, its totals without/with the pick and the cap."""

        self.ability = ability
        self.current_total = current_total
        self.requested = requested
        self.cap = cap
        super().__init__(
            f"Cannot increase {ability} to {requested}: the effective score is already {current_total} "
            f"and cannot exceed the cap of {cap}."
        )


class GrantChoiceRequiredException(AppError):
    """
    Raised when a grant (a level-up's newly-unlocked feature, an
    ASI-level feat pick, or a GM-panel feat/feature grant) has a
    "pick N of M" choice group that the caller's answers didn't resolve —
    a grant is never left silently half-materialized regardless of who
    created it.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, feature_id: int, feature_name: str, pending_group_ids: list[int]):
        """Initialize with the unresolved feature/groups."""

        self.feature_id = feature_id
        self.feature_name = feature_name
        self.pending_group_ids = pending_group_ids
        super().__init__(
            f"Feature '{feature_name}' (id {feature_id}) still has unanswered choice group(s) "
            f"{pending_group_ids} — include matching entries in the request's choice answers."
        )


class SpellPickRequiredError(AppError):
    """Raised (422) when an "any spell" (open) option is picked without naming the spell."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has an open ('any spell') spell effect — name the spell in 'spell_id'.")


class UnexpectedSpellPickError(AppError):
    """Raised (422) when an answer names a ``spell_id`` for an option that has no open spell effect."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has no open ('any spell') spell effect — 'spell_id' must not be set.")


class UnknownSpellPickError(AppError):
    """Raised (422) when an answer names spells that don't exist."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, spell_ids: list[int]):
        """Initialize with the unknown ids."""
        super().__init__(f"Unknown spell_id(s): {spell_ids}.")


class SpellPickNotAllowedError(AppError):
    """
    Raised (422) when the spell named for an open option fails the option's
    filter (class list, level, school, ritual) or the character already has it.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int, spell_id: int, reason: str):
        """Initialize with the offending option/spell and why the pick is refused."""
        super().__init__(f"Option {option_id} can't be taken with spell {spell_id}: {reason}.")


class ItemPickRequiredError(AppError):
    """Raised (422) when an "any tool" (open) option is picked without naming the tool."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has an open ('any tool') tool effect — name the tool in 'item_id'.")


class UnexpectedItemPickError(AppError):
    """Raised (422) when an answer names an ``item_id`` for an option that has no open tool effect."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has no open ('any tool') tool effect — 'item_id' must not be set.")


class ItemPickNotAllowedError(AppError):
    """Raised (422) when an open tool option names a wrong or owned tool, or a concrete one grants an owned tool."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int, item_id: int, reason: str):
        """Initialize with the offending option/item and why the pick is refused."""
        super().__init__(f"Option {option_id} can't be taken with item {item_id}: {reason}.")


class AbilityPickRequiredError(AppError):
    """Raised (422) when an "any ability/saving throw" (open) option is picked without naming the ability."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has an open ('any ability') effect — name the ability in 'ability'.")


class UnexpectedAbilityPickError(AppError):
    """Raised (422) when an answer names an ``ability`` for an option that has no open ability/saving-throw effect."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int):
        """Initialize with the offending option id."""
        super().__init__(f"Option {option_id} has no open ('any ability') effect — 'ability' must not be set.")


class AbilityPickNotAllowedError(AppError):
    """Raised (422) when the ability named for an open option is one the same option already names."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, option_id: int, ability: str):
        """Initialize with the offending option/ability."""
        super().__init__(f"Option {option_id} already names {ability} — pick another ability for its open effect.")
