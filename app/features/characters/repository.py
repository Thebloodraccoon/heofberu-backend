from sqlalchemy.orm import Session

from app.models.character_model import Character


class CharacterRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Character]:
        """Get all characters. GM-only use case."""
        return self.db.query(Character).order_by(Character.name).all()

    def get_all_by_owner(self, owner_id: int) -> list[Character]:
        """Get characters owned by a specific user. Player use case."""
        return self.db.query(Character).filter(Character.owner_id == owner_id).order_by(Character.name).all()

    def get_by_id(self, character_id: int) -> Character | None:
        return self.db.query(Character).filter(Character.id == character_id).first()

    def create(self, character_data: dict, owner_id: int) -> Character:
        character = Character(**character_data, owner_id=owner_id)
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)
        return character

    def update(self, character: Character, update_data: dict) -> Character:
        for field, value in update_data.items():
            setattr(character, field, value)

        self.db.commit()
        self.db.refresh(character)
        return character
