"""Class-specific application exceptions."""

from app.core.exceptions import AppError


class ClassNotFoundException(AppError):
    """Raised when a class with the given ID does not exist."""

    status_code = 404

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(f"Class with id {class_id} not found.")


class SubclassNotFoundException(AppError):
    status_code = 404

    def __init__(self, class_id: int, subclass_id: int):
        super().__init__(f"Subclass with id {subclass_id} not found for class {class_id}.")


class InvalidClassLevelException(AppError):
    """Raised when a spell slot progression is set for a class_level outside 1-20."""

    status_code = 400

    def __init__(self, class_level: int):
        self.class_level = class_level
        super().__init__(f"Invalid class_level '{class_level}': must be between 1 and 20.")


class SpellcastingAbilityNotPrimaryException(AppError):
    """
    Raised when updating ``primary_abilities`` would drop the class's
    existing ``spellcasting_ability`` from that list, without the request
    also explicitly setting a new ``spellcasting_ability``.
    """

    status_code = 400

    def __init__(self, spellcasting_ability, primary_abilities: list):
        self.spellcasting_ability = spellcasting_ability
        self.primary_abilities = primary_abilities
        super().__init__(
            f"Cannot update primary_abilities to {primary_abilities}: "
            f"the class's current spellcasting_ability "
            f"('{spellcasting_ability}') would no longer be a primary "
            f"ability. Pass spellcasting_ability explicitly in the same "
            f"request to change it."
        )
