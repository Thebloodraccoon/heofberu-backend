"""Skill cache namespaces: what each kind of skill write has to purge."""

from app.core.cache.namespaces import dependents

# Class/race/background details and every cached feature payload embed skill
# names (``SkillResponse`` rows, ``effects_summary``), so a skill edit must
# purge all of them.
SKILL_DEPENDENT_CACHE_NAMESPACES = dependents("skills")

# A brand-new skill is not referenced anywhere yet, and a skill can only be
# deleted once nothing references it: both only change the skill listings.
SKILL_OWN_CACHE_NAMESPACES = ("skills",)

SKILL_CACHE_NAMESPACES = SKILL_OWN_CACHE_NAMESPACES + SKILL_DEPENDENT_CACHE_NAMESPACES
