"""Class-specific HTTP exceptions."""

from fastapi import HTTPException, status


class ClassNotFoundException(HTTPException):
    """Raised when a class with the given ID does not exist."""

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class with id {class_id} not found.",
        )


class SubclassNotFoundException(HTTPException):
    def __init__(self, class_id: int, subclass_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subclass with id {subclass_id} not found for class {class_id}.",
        )


class InvalidClassLevelException(HTTPException):
    """Raised when a spell slot progression is set for a class_level outside 1-20."""

    def __init__(self, class_level: int):
        self.class_level = class_level
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid class_level '{class_level}': must be between 1 and 20.",
        )


class SpellcastingAbilityNotPrimaryException(HTTPException):
    """
    Raised when updating ``primary_abilities`` would drop the class's
    existing ``spellcasting_ability`` from that list, without the request
    also explicitly setting a new ``spellcasting_ability``.
    """

    def __init__(self, spellcasting_ability, primary_abilities: list):
        self.spellcasting_ability = spellcasting_ability
        self.primary_abilities = primary_abilities
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot update primary_abilities to {primary_abilities}: "
                f"the class's current spellcasting_ability "
                f"('{spellcasting_ability}') would no longer be a primary "
                f"ability. Pass spellcasting_ability explicitly in the same "
                f"request to change it."
            ),
        )
