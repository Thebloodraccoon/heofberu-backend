from sqlalchemy.orm import Session

from app.models.race_model import Race


class RaceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Race]:
        return self.db.query(Race).order_by(Race.name).all()

    def get_by_id(self, race_id: int) -> Race | None:
        return self.db.query(Race).filter(Race.id == race_id).first()

    def get_by_name(self, name: str) -> Race | None:
        return self.db.query(Race).filter(Race.name == name).first()

    def create(self, race_data: dict) -> Race:
        race = Race(**race_data)
        self.db.add(race)
        self.db.commit()
        self.db.refresh(race)
        return race

    def update(self, race: Race, update_data: dict) -> Race:
        for field, value in update_data.items():
            setattr(race, field, value)

        self.db.commit()
        self.db.refresh(race)
        return race
