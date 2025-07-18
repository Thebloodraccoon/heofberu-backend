from fastapi import HTTPException


class RegistrationAlreadyExistsException(HTTPException):
    def __init__(self, field: str):
        super().__init__(status_code=409, detail=f"{field.capitalize()} already used in pending registration")


class RegistrationNotFoundException(HTTPException):
    def __init__(self):
        super().__init__(status_code=404, detail="Registration not found")
