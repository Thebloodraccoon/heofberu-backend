"""Exceptions for the character crud sub-domain."""

from app.core.exceptions import AppError


class InvalidHpUpdateException(AppError):
    """
    Raised when an HP update request is malformed (e.g. mixes delta with
    absolute values, or provides neither).
    """

    status_code = 400

    def __init__(self, message: str = "Provide either 'delta' or an absolute HP value, not both."):
        super().__init__(message)


class SkillNotAvailableForClassException(AppError):
    """Raised when a skill_id is not in the class's available_skills list."""

    status_code = 400

    def __init__(self, class_id: int, skill_id: int):
        self.class_id = class_id
        self.skill_id = skill_id
        super().__init__(f"Skill {skill_id} is not available for class {class_id}.")


class TooManySkillChoicesException(AppError):
    """Raised when the number of chosen skills exceeds the class's skill_choice_count."""

    status_code = 400

    def __init__(self, class_id: int, allowed: int, requested: int):
        self.class_id = class_id
        self.allowed = allowed
        self.requested = requested
        super().__init__(f"Class {class_id} allows at most {allowed} skill choices, but {requested} were requested.")


class ItemChoicesWithoutGroupsException(AppError):
    """Raised when item_choice_ids are sent but the character's sources define no choice groups."""

    status_code = 400

    def __init__(self):
        super().__init__("Item choice options were provided, but no choice groups exist for this character's sources.")


class ItemChoiceNotAvailableException(AppError):
    """Raised when an item_choice_id is not one of the character's sources' choice-group options."""

    status_code = 400

    def __init__(self, option_id: int):
        self.option_id = option_id
        super().__init__(f"Item choice option {option_id} is not available for this character's sources.")


class TooFewItemChoicesException(AppError):
    """
    Raised when fewer (or more) options than the group's ``pick_count``
    were chosen from a starting-equipment choice group.
    """

    status_code = 400

    def __init__(self, group_id: int, pick_count: int, chosen: int):
        self.group_id = group_id
        self.pick_count = pick_count
        self.chosen = chosen
        super().__init__(
            f"Choice group {group_id} requires exactly {pick_count} selection(s), but {chosen} were chosen."
        )
