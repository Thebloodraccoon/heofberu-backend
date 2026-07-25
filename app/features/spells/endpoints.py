from fastapi import APIRouter

from app.core.dependencies import CurrentUserDep, GmUserDep, SpellServiceDep
from app.features.spells.schemas import SpellCreate, SpellResponse, SpellUpdate

router = APIRouter()


@router.get("/", response_model=list[SpellResponse])
def get_spells(spell_service: SpellServiceDep, _: CurrentUserDep):
    """List all spells. Any authenticated user (GM or player) can read."""
    return spell_service.get_all_spells()


@router.get("/{spell_id}", response_model=SpellResponse)
def get_spell(spell_id: int, spell_service: SpellServiceDep, _: CurrentUserDep):
    """Get a single spell by ID. Any authenticated user (GM or player) can read."""
    return spell_service.get_spell_by_id(spell_id)


@router.post("/", response_model=SpellResponse, status_code=201)
def create_spell(spell_data: SpellCreate, spell_service: SpellServiceDep, _: GmUserDep):
    """Create a new spell. GM only."""
    return spell_service.create_spell(spell_data)


@router.patch("/{spell_id}", response_model=SpellResponse)
def update_spell(spell_id: int, update_data: SpellUpdate, spell_service: SpellServiceDep, _: GmUserDep):
    """Update an existing spell. GM only."""
    return spell_service.update_spell(spell_id, update_data)
