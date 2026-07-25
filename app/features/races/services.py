from sqlalchemy.orm import Session

from app.exceptions.race_exceptions import RaceNameAlreadyExistsException, RaceNotFoundException
from app.features.races.repository import RaceRepository
from app.features.races.schemas import RaceCreate, RaceResponse, RaceUpdate


class RaceService:
    def __init__(self, db: Session):
        self.repository = RaceRepository(db)

    def get_all_races(self) -> list[RaceResponse]:
        races = self.repository.get_all()
        return [RaceResponse.model_validate(race) for race in races]

    def get_race_by_id(self, race_id: int) -> RaceResponse:
        race = self.repository.get_by_id(race_id)
        if not race:
            raise RaceNotFoundException(race_id=race_id)

        return RaceResponse.model_validate(race)

    def create_race(self, race_data: RaceCreate) -> RaceResponse:
        self._check_name_available(race_data.name)

        race = self.repository.create(race_data.model_dump())
        return RaceResponse.model_validate(race)

    def update_race(self, race_id: int, update_data: RaceUpdate) -> RaceResponse:
        race = self.repository.get_by_id(race_id)
        if not race:
            raise RaceNotFoundException(race_id=race_id)

        fields = update_data.model_dump(exclude_unset=True)

        if "name" in fields and fields["name"] != race.name:
            self._check_name_available(fields["name"])

        updated_race = self.repository.update(race, fields)
        return RaceResponse.model_validate(updated_race)

    def _check_name_available(self, name: str) -> None:
        if self.repository.get_by_name(name):
            raise RaceNameAlreadyExistsException(name)
