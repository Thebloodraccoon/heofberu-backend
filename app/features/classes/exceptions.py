"""Class-specific application exceptions."""

from app.core.exceptions import AppError


class ClassNotFoundException(AppError):
    """Raised when a class with the given ID does not exist."""

    status_code = 404

    def __init__(self, class_id: int):
        """Store the missing class id in the error message."""

        self.class_id = class_id
        super().__init__(f"Class with id {class_id} not found.")


class SubclassNotFoundException(AppError):
    """Raised when a subclass does not exist for the given class."""

    status_code = 404

    def __init__(self, class_id: int, subclass_id: int):
        """Compose a message from the class and subclass ids."""

        super().__init__(f"Subclass with id {subclass_id} not found for class {class_id}.")


class InvalidClassLevelException(AppError):
    """Raised when a spell slot progression is set for a class_level outside 1-20."""

    status_code = 400

    def __init__(self, class_level: int):
        """Compose a message for the invalid class level."""

        self.class_level = class_level
        super().__init__(f"Invalid class_level '{class_level}': must be between 1 and 20.")
