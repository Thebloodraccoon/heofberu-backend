"""Shared helpers for character unit tests."""

from types import SimpleNamespace


def make_feat_with_choice_groups(
    ability_effects=None,
    *,
    prerequisite_ability=None,
    prerequisite_minimum_score=None,
    prerequisite_description="",
    min_level=None,
):
    """Build a feat-shaped SimpleNamespace using the engine's choice_groups form.

    ability_effects: list of (ability, amount) tuples.
    One choice_group with pick_count=1 is created when there are effects.
    """
    options = [
        SimpleNamespace(
            id=100 + i,
            sort_order=i,
            ability_effects=[SimpleNamespace(id=200 + i, ability=a, amount=amt)],
        )
        for i, (a, amt) in enumerate(ability_effects or [])
    ]
    groups = [SimpleNamespace(id=1, pick_count=1, options=options)] if options else []
    return SimpleNamespace(
        id=2,
        name="Tough",
        description="More hit points.",
        choice_groups=groups,
        prerequisite_ability=prerequisite_ability,
        prerequisite_minimum_score=prerequisite_minimum_score,
        prerequisite_description=prerequisite_description,
        min_level=min_level,
    )
