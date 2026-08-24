"""Race CRUD endpoints: paginated listing, get, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.constants import RaceSize
from app.core.base.service import Page
from app.features.races.dependencies import RaceCrudDep
from app.features.races.schemas import RaceCreate, RaceGetAllResponse, RaceResponse, RaceUpdate
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[RaceGetAllResponse],
    summary="List races",
)
async def get_races(
    race_service: RaceCrudDep,
    race_size: list[RaceSize] | None = Query(None, description="Any-of match on the race's size (repeat the key: `?race_size=SMALL&race_size=MEDIUM`)."),
    search: str | None = Query(None, description="Case-insensitive substring match against the race's name."),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of races with only `id`, `name`, and `size`.

    Open endpoint, no authentication required.

    `race_size` is an any-of match (repeat the key, e.g.
    `race_size=SMALL&race_size=MEDIUM`). `search` is a
    case-insensitive partial match against the race name; both can be
    combined.

    Response is `{items, total, page, size}` — `total` is the count of
    matching races across every page, not just this one.

    Does not include ability bonuses or granted skills — use
    `GET /races/{race_id}` for the full record.
    """

    return await race_service.get_all(page=page, size=size, filters={"size": race_size}, search=search)


@router.get(
    "/{race_id:int}",
    response_model=RaceResponse,
    summary="Get a race by ID",
    responses={
        404: {"description": "Race with id not found."},
    },
)
async def get_race(race_id: int, race_service: RaceCrudDep):
    """
    Return a single race by ID, with full detail — including ability
    bonuses and granted skills.

    Open endpoint, no authentication required.
    """

    return await race_service.get_by_id(race_id)


@router.post(
    "",
    response_model=RaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a race",
    responses={
        409: {"description": "A race with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
async def create_race(
    data: Annotated[
        RaceCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Minimal — base fields only",
                    "value": {
                        "name": "Elf",
                        "size": "MEDIUM",
                        "speed": 30,
                    },
                },
                "with_bonuses_and_skills": {
                    "summary": "With ability bonuses and granted skills",
                    "value": {
                        "name": "Elf",
                        "size": "MEDIUM",
                        "speed": 30,
                        "ability_bonuses": [{"ability": "DEX", "bonus": 2}],
                        "granted_skills": [3, 7],
                    },
                },
            },
        ),
    ],
    race_service: RaceCrudDep,
    current_user: GmUserDep,
):
    """
    Create a new race. **GM only.**

    `ability_bonuses` and `granted_skills` are optional. If provided,
    they're saved together with the race in a single transaction — the
    race is fully set up in one call instead of a `POST` followed by two
    `PUT` calls.
    """

    return await race_service.create_race(data, created_by_id=current_user.id)


@router.patch(
    "/{race_id:int}",
    response_model=RaceResponse,
    summary="Update a race's base fields",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Another race already uses the requested name."},
    },
)
async def update_race(
    race_id: int,
    data: Annotated[
        RaceUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the race and edit its description",
                    "value": {
                        "name": "Elf",
                        "description": "Graceful and long-lived, with keen senses.",
                    },
                },
                "change-speed": {
                    "summary": "Adjust base walking speed",
                    "value": {"speed": 35},
                },
            }
        ),
    ],
    race_service: RaceCrudDep,
    _: GmUserDep,
):
    """
    Partially update a race's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch ability bonuses or granted skills — use
    `PUT /races/{race_id}/ability-bonuses` and `PUT /races/{race_id}/skills`
    for those.
    """

    return await race_service.update(race_id, data)


@router.delete(
    "/{race_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a race",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Race is still in use by one or more characters."},
    },
)
async def delete_race(race_id: int, race_service: RaceCrudDep, _: FounderDep):
    """
    Delete a race. **Founder only.**

    Also removes its ability bonuses, granted skills, subraces, and
    features (cascade). Blocked if the race is still assigned to one or
    more characters.
    """

    await race_service.delete(race_id)
    return None
